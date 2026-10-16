"""M3 模块 2 端到端：OCR 失败续跑（K5）+ 陈旧结果处置（K4）。

为什么用**桩引擎**而不是真跑 OCR（见 plan/verify §四 坑 7）：真识别 ~5.6s/图，
失败/续跑/陈旧这些**控制流**断言不需要真模型，桩可精确注入"某张必然失败"与
"识别结果是什么"，把控制流与识别质量分开验证。真跑留给端到端冒烟。

K5（失败不中断 + `ocr_tries` 递增 + `--retry-failed` 续跑）与 K4（陈旧结果不得
被消费/不得落库）都是**已锁口径**，本文件是它们此前缺失的端到端覆盖。
"""

import os
import time

import pytest
from PIL import Image

from picrecall import cli, config, db, index, ocr, search


def _png(folder, name, color="white", size=(40, 20)):
    p = folder / name
    Image.new("RGB", size, color).save(str(p))
    return str(p)


def _stub_engine(monkeypatch, handler):
    """把引擎与单张识别打桩：`handler(path)` 返回 lines 或抛异常。"""
    monkeypatch.setattr(ocr, "load_engine", lambda: object())

    def fake_one(engine, path):
        lines = handler(path)
        return [{"text": t, "conf": 0.99} for t in lines], 0.99

    monkeypatch.setattr(ocr, "ocr_one", fake_one)


def _rows(conn):
    return {
        os.path.basename(r["path"]): (r["status"], r["ocr_tries"], r["ocr_error"])
        for r in conn.execute("SELECT path, status, ocr_tries, ocr_error FROM files")
    }


# ── K5：失败隔离 + 续跑 ────────────────────────────────────────────────────

def test_failed_image_does_not_abort_batch_and_is_observable(tmp_path, monkeypatch):
    """单张失败：整批**不中断**，其余图仍 indexed；该图 ocr_failed/ocr_tries==1/ocr_error 非空。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    for name in ("a.png", "b.png", "c.png"):
        _png(folder, name)

    def handler(path):
        if os.path.basename(path) == "b.png":
            raise RuntimeError("cannot identify image file")
        return ["本月账单已生成"]

    _stub_engine(monkeypatch, handler)

    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        report = ocr.ocr_pending(conn)
        rows = _rows(conn)
    finally:
        conn.close()

    assert report["ok"] == 2 and report["failed"] == 1, "失败未隔离或整批中断: %s" % report
    assert rows["a.png"][0] == "indexed" and rows["c.png"][0] == "indexed", \
        "失败项以外的图未完成识别（整批被中断）"
    assert rows["b.png"][0] == "ocr_failed"
    assert rows["b.png"][1] == 1, "ocr_tries 未递增（续跑不可观测）"
    assert rows["b.png"][2], "ocr_error 未记录失败原因"


def test_retry_failed_increments_tries_without_recounting_successes(tmp_path, monkeypatch):
    """`--retry-failed` 续跑：失败项 ocr_tries 递增到 2，**不重复计**已成功项。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    for name in ("a.png", "b.png"):
        _png(folder, name)

    _stub_engine(monkeypatch, lambda path: (_ for _ in ()).throw(RuntimeError("boom"))
                 if os.path.basename(path) == "b.png" else ["本月账单已生成"])

    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        first = ocr.ocr_pending(conn)
        assert first["ok"] == 1 and first["failed"] == 1

        # 续跑：只有失败项被重新纳入（a.png 已 indexed，不再计）
        second = ocr.ocr_pending(conn, retry_failed=True)
        rows = _rows(conn)
    finally:
        conn.close()

    assert second["considered"] == 1, "续跑把已成功项重新纳入 = 重复计: %s" % second
    assert second["ok"] == 0 and second["failed"] == 1
    assert rows["b.png"][1] == 2, "ocr_tries 未随续跑递增"
    assert rows["a.png"][1] == 0, "已成功项的 tries 被无端改动"


def test_retry_failed_after_fix_becomes_indexed(tmp_path, monkeypatch):
    """修好失败图后 `--retry-failed` → 变 indexed，且其文本可被检索。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    for name in ("a.png", "b.png"):
        _png(folder, name)

    state = {"broken": True}

    def handler(path):
        if os.path.basename(path) == "b.png" and state["broken"]:
            raise RuntimeError("cannot identify image file")
        return ["转账成功"] if os.path.basename(path) == "b.png" else ["本月账单已生成"]

    _stub_engine(monkeypatch, handler)

    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        ocr.ocr_pending(conn)
        assert _rows(conn)["b.png"][0] == "ocr_failed"

        state["broken"] = False                      # 图被"修好"
        fixed = ocr.ocr_pending(conn, retry_failed=True)
        rows = _rows(conn)
        hits = search.search(conn, "转账成功")
    finally:
        conn.close()

    assert fixed["ok"] == 1 and fixed["failed"] == 0
    assert rows["b.png"][0] == "indexed", "修复后续跑未恢复为 indexed"
    assert len(hits) == 1 and os.path.basename(hits[0]["path"]) == "b.png", \
        "续跑成功后其文本未被检索到"


def test_cli_ocr_reports_findings_on_failure(tmp_path, monkeypatch):
    """CLI 层：有失败项 → exit 1（检出问题，非跑挂），且提示可续跑。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    _png(folder, "a.png")
    _png(folder, "b.png")
    _stub_engine(monkeypatch, lambda path: (_ for _ in ()).throw(RuntimeError("boom"))
                 if os.path.basename(path) == "b.png" else ["本月账单已生成"])

    dbp = str(tmp_path / "i.db")
    assert cli.main(["index", str(folder), "--db", dbp]) == config.EXIT_OK
    assert cli.main(["ocr", "--db", dbp]) == config.EXIT_FINDINGS


# ── K4：陈旧结果不得被消费 / 不得落库 ──────────────────────────────────────

def test_content_change_invalidates_stale_text_before_reocr(tmp_path, monkeypatch):
    """内容变更 → 旧 OCR 文本**即时作废**，不得在重识别前继续被检索到。

    这是 K4"防陈旧结果覆盖新内容"的**消费侧**：若旧 chunk/ocr_text 留着，
    `search` 会命中一张图里**已经没有的文字**——用户搜到的是假命中。
    """
    folder = tmp_path / "shots"
    folder.mkdir()
    p = _png(folder, "a.png", "white")

    _stub_engine(monkeypatch, lambda path: ["本月账单已生成"])

    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        ocr.ocr_pending(conn)
        assert len(search.search(conn, "账单")) == 1

        # 内容变更（尚未重识别）
        time.sleep(0.01)
        Image.new("RGB", (40, 20), "black").save(p)
        result = index.apply_scan(conn, index.scan_folder(str(folder)))
        assert result["changed"] == 1

        derived = conn.execute(
            "SELECT (SELECT COUNT(*) FROM ocr_text) AS o, "
            "        (SELECT COUNT(*) FROM chunk) AS c, "
            "        (SELECT COUNT(*) FROM chunk_fts) AS f"
        ).fetchone()
        hits = search.search(conn, "账单")
    finally:
        conn.close()

    assert (derived["o"], derived["c"], derived["f"]) == (0, 0, 0), \
        "内容变更后旧派生行未作废（search 会继续命中已不存在的文字）"
    assert hits == [], "陈旧文本在重识别前仍被检索到"


def test_content_change_then_reocr_rebinds_text_and_sig(tmp_path, monkeypatch):
    """内容变更 → 重识别后：新文本可检索、旧文本消失、`run_sig` 随输入更新。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    p = _png(folder, "a.png", "white")

    state = {"lines": ["本月账单已生成"]}
    _stub_engine(monkeypatch, lambda path: state["lines"])

    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        ocr.ocr_pending(conn)
        sig_before = ocr.get_ocr_text(conn, 1)["run_sig"]

        time.sleep(0.01)
        Image.new("RGB", (40, 20), "black").save(p)
        index.apply_scan(conn, index.scan_folder(str(folder)))

        state["lines"] = ["转账成功"]
        ocr.ocr_pending(conn)
        stored = ocr.get_ocr_text(conn, 1)
        sig_after = stored["run_sig"]
        new_hits = search.search(conn, "转账成功")
        old_hits = search.search(conn, "账单")
    finally:
        conn.close()

    assert stored["text"] == "转账成功", "重识别未写入新文本"
    assert sig_after != sig_before, "run_sig 未随输入（内容）变化而更新"
    assert len(new_hits) == 1 and old_hits == [], \
        "重识别后新旧文本的检索可见性不正确"


def test_ocr_refuses_to_store_when_disk_drifted_from_ledger(tmp_path, monkeypatch):
    """扫描后文件被改动、**未重索引** → 本次结果不落库（不覆盖），报告需重建。

    这是 K4 的**写入侧**：若照旧落库，就会出现"结果声称属于旧内容、文本却来自新内容"
    的错绑，且 `run_sig` 记录的是一个不再描述该图的身份。
    """
    folder = tmp_path / "shots"
    folder.mkdir()
    p = _png(folder, "a.png", "white")

    _stub_engine(monkeypatch, lambda path: ["转账成功"])

    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        # 扫描之后、识别之前改动磁盘内容（不重跑 index）
        time.sleep(0.01)
        Image.new("RGB", (40, 20), "red").save(p)

        report = ocr.ocr_pending(conn)
        row = conn.execute("SELECT status, ocr_error, ocr_tries FROM files").fetchone()
        n_ocr = conn.execute("SELECT COUNT(*) n FROM ocr_text").fetchone()["n"]
        hits = search.search(conn, "转账成功")
    finally:
        conn.close()

    assert report["stale"] == 1 and report["ok"] == 0, "陈旧输入未被拒绝落库: %s" % report
    assert row["status"] == "pending", "被拒绝后应留在待识别态"
    assert "输入已变" in (row["ocr_error"] or ""), "未记录'需重建'原因"
    assert row["ocr_tries"] == 0, "陈旧拒绝不是识别失败，不应计 tries"
    assert n_ocr == 0 and hits == [], "陈旧结果被落库并成为可检索内容"


def test_cli_ocr_reports_stale_as_findings(tmp_path, monkeypatch):
    """CLI 层：有陈旧项 → exit 1，且提示先重跑 index。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    p = _png(folder, "a.png", "white")
    _stub_engine(monkeypatch, lambda path: ["转账成功"])

    dbp = str(tmp_path / "i.db")
    assert cli.main(["index", str(folder), "--db", dbp]) == config.EXIT_OK
    time.sleep(0.01)
    Image.new("RGB", (40, 20), "red").save(p)
    assert cli.main(["ocr", "--db", dbp]) == config.EXIT_FINDINGS


@pytest.mark.parametrize("field,new_value", [
    ("engine", "rapidocr-onnxruntime/9.9.9"),
    ("profile", config.PROFILE_SIMPLE),
    ("conf", 0.99),
])
def test_run_sig_covers_every_input_dimension(field, new_value):
    """K4：输入身份的**每一维**（内容/引擎/profile/阈值）都改变签名——签名漏维即失效。"""
    base = dict(file_hash="h", engine_ver="rapidocr-onnxruntime/1.4.4",
                profile=config.PROFILE_CHAR, conf_min=config.OCR_CONF_MIN)
    sig = ocr.compute_run_sig(**base)
    changed = dict(base)
    changed[{"engine": "engine_ver", "profile": "profile", "conf": "conf_min"}[field]] = new_value
    assert ocr.compute_run_sig(**changed) != sig, "%s 未参与签名" % field
    assert ocr.compute_run_sig(**base) == sig, "签名不确定"
