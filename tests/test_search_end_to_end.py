"""M3 模块 3 端到端：检索命中、排序稳定、profile 契约、limit 边界。

补的是 `test_segment.py`（单测级、内存库）**没有**的那一层：真建库 → 真入库 →
`search`（含 CLI 形态）。K6（profile 不匹配 exit 2）与 K7（排序 `rank, path, line_no`）
都是已锁口径，本文件给它们端到端形态与**确定性**断言。

桩引擎的理由同 `test_ocr_pipeline.py`：真 OCR ~5.6s/图，检索/排序逻辑不需要真模型。
"""

import os
import time

from PIL import Image

from picrecall import cli, config, db, index, ocr, search


def _png(folder, name, color="white"):
    p = folder / name
    Image.new("RGB", (40, 20), color).save(str(p))
    return str(p)


def _stub_engine(monkeypatch, mapping):
    """mapping: 文件名 → 该图的行文本列表。"""
    monkeypatch.setattr(ocr, "load_engine", lambda: object())

    def fake_one(engine, path):
        lines = mapping.get(os.path.basename(path), [])
        return [{"text": t, "conf": 0.99} for t in lines], 0.99

    monkeypatch.setattr(ocr, "ocr_one", fake_one)


def _build(tmp_path, monkeypatch, mapping, profile=None):
    """建真库 + 桩识别，返回 (conn, folder)。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    for name in mapping:
        _png(folder, name)
    _stub_engine(monkeypatch, mapping)
    conn = db.connect(str(tmp_path / "i.db"))
    index.apply_scan(conn, index.scan_folder(str(folder)))
    db.set_meta(conn, "tokenizer_profile", profile or config.PROFILE_CHAR)
    ocr.ocr_pending(conn, profile=profile or config.PROFILE_CHAR)
    return conn, folder


# ── K6 + 短中文查询端到端 ──────────────────────────────────────────────────

def test_short_chinese_query_hits_end_to_end(tmp_path, monkeypatch):
    """端到端：真建库 → 入库 → `search "账单"` 命中预期图（此前只有单测级覆盖）。"""
    mapping = {
        "bill.png": ["本月账单已生成", "请及时缴纳"],
        "chat.png": ["今晚八点见", "路上堵车了"],
        "code.png": ["ModuleNotFoundError: config error"],
    }
    conn, folder = _build(tmp_path, monkeypatch, mapping)
    try:
        hits = search.search(conn, "账单")
    finally:
        conn.close()

    assert len(hits) == 1, "2 字中文查询未命中预期图: %s" % [h["path"] for h in hits]
    assert os.path.basename(hits[0]["path"]) == "bill.png"
    assert hits[0]["text"] == "本月账单已生成", "命中展示的必须是原文"
    assert "[账单]" in hits[0]["snippet"], "片段未在原文上高亮命中"


def test_short_chinese_query_does_not_over_match(tmp_path, monkeypatch):
    """子串语义的**边界**：只命中真含该子串的图，不误召回无关图。"""
    mapping = {
        "bill.png": ["本月账单已生成"],
        "other.png": ["本月话费已生成"],
        "bill2.png": ["账单明细如下"],
    }
    conn, folder = _build(tmp_path, monkeypatch, mapping)
    try:
        hits = search.search(conn, "账单")
    finally:
        conn.close()

    got = {os.path.basename(h["path"]) for h in hits}
    assert got == {"bill.png", "bill2.png"}, "子串命中集不正确: %s" % sorted(got)


def test_profile_mismatch_is_exit_2_end_to_end(tmp_path, monkeypatch, capsys):
    """K6 端到端：库记录 profile=char，查询请求 simple → exit 2 并提示重建。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    _png(folder, "a.png")
    _stub_engine(monkeypatch, {"a.png": ["本月账单已生成"]})

    dbp = str(tmp_path / "i.db")
    assert cli.main(["index", str(folder), "--db", dbp, "--profile", config.PROFILE_CHAR]) == config.EXIT_OK
    assert cli.main(["ocr", "--db", dbp]) == config.EXIT_OK

    code = cli.main(["search", "账单", "--db", dbp, "--profile", config.PROFILE_SIMPLE])
    err = capsys.readouterr().err
    assert code == config.EXIT_USAGE, "profile 不匹配未走 exit 2"
    assert "profile" in err and "重建" in err, "未给出可操作提示: %r" % err


def test_matching_profile_is_exit_0_end_to_end(tmp_path, monkeypatch):
    """对照：profile 与库一致时正常命中（证明上一条的红来自不匹配而非检索失效）。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    _png(folder, "a.png")
    _stub_engine(monkeypatch, {"a.png": ["本月账单已生成"]})

    dbp = str(tmp_path / "i.db")
    assert cli.main(["index", str(folder), "--db", dbp, "--profile", config.PROFILE_CHAR]) == config.EXIT_OK
    assert cli.main(["ocr", "--db", dbp]) == config.EXIT_OK
    assert cli.main(["search", "账单", "--db", dbp, "--profile", config.PROFILE_CHAR]) == config.EXIT_OK


# ── K7：排序稳定性 ─────────────────────────────────────────────────────────

def _seq(hits):
    """把命中序列压成可逐项比较的元组（含顺序）。"""
    return [(os.path.basename(h["path"]), h["line_no"]) for h in hits]


def test_query_double_run_is_itemwise_identical(tmp_path, monkeypatch):
    """同库同 query 双跑 → 返回序列**逐项相等**（含顺序）。"""
    mapping = {
        "b.png": ["本月账单已生成", "账单明细"],
        "a.png": ["账单提醒", "本月账单已生成"],
        "c.png": ["无关内容"],
    }
    conn, folder = _build(tmp_path, monkeypatch, mapping)
    try:
        first = search.search(conn, "账单")
        second = search.search(conn, "账单")
    finally:
        conn.close()

    assert _seq(first) == _seq(second), "双跑序列不一致（排序不确定）"
    assert first, "样例无命中，断言不具区分度"


def test_tie_break_by_path_when_rowid_order_differs(tmp_path, monkeypatch):
    """K7 tie-breaker：rank 并列时按 `path` 决定性排序——即便 FTS rowid 序与之相反。

    单纯"先插 b、后插 a"**没有区分度**：`ocr_pending` 按 `ORDER BY path` 遍历，
    插入序恰好等于路径序，`ORDER BY rank` 单独也碰巧给出同一顺序。

    真正有区分度的构造是一条**真实可达**的流程：先全量识别，再让**路径靠前**的那张图
    重识别（内容变更 → 派生行作废 → 重建 chunk）。重建后它的 FTS rowid 变得**最新**，
    于是"rowid 序"与"路径序"相反——此时只有 `path` tie-breaker 才能给出正确顺序。

    变异验证：把 `ORDER BY rank, f.path, c.line_no` 改成 `ORDER BY rank` → 本测试必红。
    """
    mapping = {"a.png": ["本月账单已生成"], "b.png": ["本月账单已生成"]}
    folder = tmp_path / "shots"
    folder.mkdir()
    for name in mapping:
        _png(folder, name)
    _stub_engine(monkeypatch, mapping)

    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        ocr.ocr_pending(conn)

        # 让 a.png 内容变更并重识别：其 chunk 行被重建 → rowid 变新（> b.png 的）
        time.sleep(0.01)
        Image.new("RGB", (40, 20), "black").save(str(folder / "a.png"))
        index.apply_scan(conn, index.scan_folder(str(folder)))
        ocr.ocr_pending(conn)

        rowids = {
            os.path.basename(r["path"]): r["rid"]
            for r in conn.execute(
                "SELECT f.path, chunk_fts.rowid AS rid FROM chunk_fts "
                "JOIN chunk c ON c.id = chunk_fts.rowid JOIN files f ON f.id = c.file_id"
            )
        }
        hits = search.search(conn, "账单")
        ranks = {h["rank"] for h in hits}
    finally:
        conn.close()

    # 前提校验：rowid 序必须与路径序**相反**，否则断言无区分度
    assert rowids["a.png"] > rowids["b.png"], \
        "构造未使 rowid 序与路径序相反，本测试将无区分度"
    assert len(ranks) == 1, "样例未构成 rank 并列，tie-breaker 断言无信息量（bm25 变了？）"
    assert [os.path.basename(h["path"]) for h in hits] == ["a.png", "b.png"], \
        "rank 并列时未按路径字典序定序（K7 tie-breaker 失效）"


def test_tie_break_by_line_no_within_same_file(tmp_path, monkeypatch):
    """同图内 rank 并列 → 按 `line_no` 升序（tie-breaker 的第二级）。

    三行文本**完全相同**（实测 bm25 才逐位相等；行长不同则分数不同，见上一测试），
    故只有 `line_no` 能定序。
    """
    mapping = {"a.png": ["账单明细", "账单明细", "账单明细"]}
    conn, folder = _build(tmp_path, monkeypatch, mapping)
    try:
        hits = search.search(conn, "账单")
        ranks = {h["rank"] for h in hits}
    finally:
        conn.close()

    assert [h["line_no"] for h in hits] == [0, 1, 2], "同图内未按 line_no 定序"
    assert len(ranks) == 1, "样例未构成 rank 并列，断言无信息量"


def test_tie_break_survives_reindex_and_reorder(tmp_path, monkeypatch):
    """决定性排序的**强断言**：把入库顺序倒过来重建，命中序列仍逐项相同。

    若排序依赖 rowid/插入序（而非 `path, line_no`），倒序入库会改变结果顺序。
    """
    mapping = {"a.png": ["本月账单已生成"], "b.png": ["本月账单已生成"]}

    conn1, _ = _build(tmp_path, monkeypatch, mapping)
    try:
        first = _seq(search.search(conn1, "账单"))
    finally:
        conn1.close()

    # 倒序建库：先插 b.png，再插 a.png
    folder2 = tmp_path / "shots2"
    folder2.mkdir()
    _png(folder2, "b.png")
    time.sleep(0.01)
    _png(folder2, "a.png")
    _stub_engine(monkeypatch, mapping)
    conn2 = db.connect(str(tmp_path / "i2.db"))
    try:
        index.apply_scan(conn2, index.scan_folder(str(folder2)))
        ocr.ocr_pending(conn2)
        second = _seq(search.search(conn2, "账单"))
    finally:
        conn2.close()

    assert first == second, "入库顺序改变了命中顺序 → 排序不是决定性的"


# ── limit 边界 ─────────────────────────────────────────────────────────────

def test_large_limit_returns_all_hits(tmp_path, monkeypatch):
    """大 limit：返回全部命中，不被截断、不报错。"""
    mapping = {"a.png": ["账单 1"], "b.png": ["账单 2"], "c.png": ["账单 3"]}
    conn, folder = _build(tmp_path, monkeypatch, mapping)
    try:
        hits = search.search(conn, "账单", limit=10 ** 6)
        default_hits = search.search(conn, "账单")
    finally:
        conn.close()

    assert len(hits) == 3, "大 limit 未返回全部命中: %d" % len(hits)
    assert _seq(hits) == _seq(default_hits), "limit 改变了命中内容或顺序"


def test_hits_over_limit_are_truncated_deterministically(tmp_path, monkeypatch):
    """命中数 > limit → 截断到 limit，且截断的是**序列前缀**（确定性）。"""
    mapping = {"c.png": ["账单"], "a.png": ["账单"], "b.png": ["账单"], "d.png": ["账单"]}
    conn, folder = _build(tmp_path, monkeypatch, mapping)
    try:
        full = search.search(conn, "账单", limit=100)
        capped = search.search(conn, "账单", limit=2)
        capped_again = search.search(conn, "账单", limit=2)
    finally:
        conn.close()

    assert len(full) == 4 and len(capped) == 2, "limit 截断行为不符: %d/%d" % (len(full), len(capped))
    assert _seq(capped) == _seq(full)[:2], "截断不是全序列前缀（截断不确定）"
    assert _seq(capped) == _seq(capped_again), "同 limit 双跑不一致"


def test_zero_hits_is_exit_0_and_empty(tmp_path, monkeypatch):
    """零命中 = 合法空结果（K8）：返回 []、exit 0。"""
    mapping = {"a.png": ["本月账单已生成"]}
    conn, folder = _build(tmp_path, monkeypatch, mapping)
    try:
        hits = search.search(conn, "不存在的词")
    finally:
        conn.close()
    assert hits == []

    folder2 = tmp_path / "shots2"
    folder2.mkdir()
    _png(folder2, "a.png")
    _stub_engine(monkeypatch, {"a.png": ["本月账单已生成"]})
    dbp = str(tmp_path / "j.db")
    assert cli.main(["index", str(folder2), "--db", dbp]) == config.EXIT_OK
    assert cli.main(["ocr", "--db", dbp]) == config.EXIT_OK
    assert cli.main(["search", "不存在的词", "--db", dbp]) == config.EXIT_OK


def test_missing_files_are_excluded_from_search(tmp_path, monkeypatch):
    """`missing` 文件不得出现在检索结果里（K3 与 K7 的交叉面）。"""
    mapping = {"a.png": ["本月账单已生成"], "b.png": ["本月账单已生成"]}
    conn, folder = _build(tmp_path, monkeypatch, mapping)
    try:
        os.remove(str(folder / "a.png"))
        index.apply_scan(conn, index.scan_folder(str(folder)))
        hits = search.search(conn, "账单")
    finally:
        conn.close()

    assert [os.path.basename(h["path"]) for h in hits] == ["b.png"], \
        "已失效(missing)的文件仍被检索到"
