"""M4 规则驱动层（plan/05 §4.3）+ 分 profile 门槛 + bench 报告可复跑。

本文件守的是 M4 的核心机制纪律：**规则驱动层不得读 manifest**。

为什么这条要单独守（K14 的延伸）：规则驱动层的全部价值在于"专治**样本没覆盖**的端点"
——它自造构造上已知的输入（空白/单字符/超长/坏图/空文件夹/无命中查询），期望由机制
直接推出。一旦它也去读 manifest，就退化成"第二个样本层"，**覆盖样本外端点**的能力归零。
故这里**三重证伪**：源码不得引用 manifest（AST）、把 manifest 定位打成抛异常仍同结论、
把 manifest 文件删掉仍同结论。

OCR 相关探针用**桩引擎**（M3 坑 3 的延伸：真识别 ~5.6s/图，控制流断言不必真跑模型），
真 OCR 的端到端留给 `plan/verify` §M4 三的冒烟。
"""

import ast
import json
import os

import pytest

from picrecall import bench, config, db, index, ocr

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# 桩引擎对规则层探针图的"拟真"回答：键是探针文件名（bench 内固定，见
# `_write_rule_probe_images`）。空白图 → 0 行；单字符图 → 该字符；超长图 → 多行；
# 坏图 → 抛异常（模拟真引擎的 LoadImageError）。
_STUB_BY_NAME = {
    "probe_blank.png": [],
    "probe_single.png": [bench.RULE_PROBE_SINGLE_CHAR],
    "probe_long.png": [bench.RULE_PROBE_LONG_LINE] * bench.RULE_PROBE_LONG_LINES,
}


def _stub_rule_engine(monkeypatch):
    """把 OCR 打桩成"对探针图给出拟真结果"（坏图抛异常，走 K5 失败隔离）。"""
    monkeypatch.setattr(ocr, "load_engine", lambda: object())

    def fake_one(engine, path):
        name = os.path.basename(path)
        if name not in _STUB_BY_NAME:
            raise RuntimeError("cannot identify image file")
        lines = _STUB_BY_NAME[name]
        return [{"text": t, "conf": 0.99} for t in lines], 0.99

    monkeypatch.setattr(ocr, "ocr_one", fake_one)


def _conn(tmp_path):
    return db.connect(str(tmp_path / "probe.db"))


# ── ① 规则层"不读 manifest"：源码级 + 运行级双重证伪 ─────────────────────

_RULE_LAYER_FUNCS = (
    "run_rule_probes", "_write_rule_probe_images", "_rule_predicates",
    "_is_blank_observation", "_within_line_bound", "_observed",
)


def _rule_layer_source():
    """把规则层各函数的**源码段**拼起来（用于 AST 证伪）。"""
    with open(bench.__file__, "r", encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    chunks = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _RULE_LAYER_FUNCS:
            chunks.append(ast.get_source_segment(src, node))
    assert len(chunks) == len(_RULE_LAYER_FUNCS), "规则层函数缺失: %s" % (chunks,)
    return "\n".join(chunks)


def test_rule_layer_source_never_references_manifest():
    """AST 守门：规则层**代码**不得出现 `manifest` 标识符，也不得调用 manifest 定位。

    只查 AST 的 Name/Attribute（不查字符串字面量）——docstring 里说明"不读 manifest"
    是文档而非行为，不该被误判。
    """
    src = _rule_layer_source()
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and "manifest" in node.id.lower():
            offenders.append("Name:%s" % node.id)
        if isinstance(node, ast.Attribute) and "manifest" in node.attr.lower():
            offenders.append("Attribute:%s" % node.attr)
    assert offenders == [], "规则层源码引用了 manifest（该层必须不读真值文件）: %s" % offenders


def test_rule_layer_conclusion_unchanged_when_manifest_locator_explodes(tmp_path, monkeypatch):
    """把 manifest 定位打成**抛异常** → 规则层结论必须逐项不变。

    这是"不读 manifest"的**运行级**证伪：若本层偷偷读了真值，这里必然抛出来。
    """
    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        baseline = bench.run_rule_probes(conn)

        def boom(*_a, **_k):
            raise AssertionError("规则层不应定位 manifest")

        monkeypatch.setattr(bench, "_resolve_manifest", boom)
        after = bench.run_rule_probes(conn)
    finally:
        conn.close()

    assert after["probes"] == baseline["probes"], "规则层结论随 manifest 定位方式变化"
    assert after["passed"] is True


def test_rule_layer_conclusion_unchanged_when_manifest_file_deleted(tmp_path, monkeypatch):
    """把真值 manifest **删掉** → 规则层结论必须逐项不变（HANDOFF-M4 §二 1 的硬要求）。"""
    _stub_rule_engine(monkeypatch)
    out = tmp_path / "synth"
    bench.gen_synthetic(str(out), data_dir=DATA_DIR, seed=20261016, count=2)

    conn = _conn(tmp_path)
    try:
        baseline = bench.run_rule_probes(conn)
        os.remove(str(out / "manifest.json"))
        after = bench.run_rule_probes(conn)
    finally:
        conn.close()

    assert after["probes"] == baseline["probes"], "删掉 manifest 后规则层结论变了"
    assert after["passed"] is True


# ── ② 规则层各端点的机制结论（样本层覆盖不到的边界）────────────────────

def _probe(result, name):
    for p in result["probes"]:
        if p["name"] == name:
            return p
    raise AssertionError("探针缺失: %s（实有 %s）" % (name, [p["name"] for p in result["probes"]]))


def test_blank_image_yields_zero_lines(tmp_path, monkeypatch):
    """全空白图 → 非空文本行必须为 0（无文本像素不应产生文本行）。"""
    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        result = bench.run_rule_probes(conn)
    finally:
        conn.close()
    assert _probe(result, "blank_image_yields_no_text_line")["ok"] is True


def test_single_char_is_detected_and_searchable(tmp_path, monkeypatch):
    """单字符图 → 命中其字符，且该字符可被检索到（端到端，不只"检出"）。"""
    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        result = bench.run_rule_probes(conn)
    finally:
        conn.close()
    p = _probe(result, "single_char_is_detected_and_searchable")
    assert p["ok"] is True, p["detail"]
    assert "检索命中=True" in p["detail"]


def test_long_text_does_not_crash_and_lines_are_bounded(tmp_path, monkeypatch):
    """超长文本图 → 状态非 ocr_failed 且行数落在 [1, 上界] 内（有界不崩）。"""
    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        result = bench.run_rule_probes(conn)
    finally:
        conn.close()
    p = _probe(result, "long_text_does_not_crash_and_lines_bounded")
    assert p["ok"] is True, p["detail"]


def test_corrupt_image_survives_index_and_search_is_empty(tmp_path, monkeypatch):
    """坏图 → 索引不中断（台账行仍在、非 missing），检索不崩且无命中。"""
    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        result = bench.run_rule_probes(conn)
    finally:
        conn.close()
    assert _probe(result, "corrupt_image_survives_index_and_search_is_empty")["ok"] is True


def test_empty_folder_indexes_cleanly_and_search_is_empty(tmp_path, monkeypatch):
    """空文件夹 → 索引不崩、库内 0 文件、检索返回空。"""
    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        result = bench.run_rule_probes(conn)
    finally:
        conn.close()
    assert _probe(result, "empty_folder_indexes_cleanly_and_search_is_empty")["ok"] is True


def test_absent_and_tokenless_queries_return_empty(tmp_path, monkeypatch):
    """无命中查询 / 无 token 查询 → 必须返回空且不崩（零命中是合法空结果，K8）。"""
    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        result = bench.run_rule_probes(conn)
    finally:
        conn.close()
    assert _probe(result, "absent_and_tokenless_queries_return_empty")["ok"] is True


def test_rule_layer_report_is_path_free(tmp_path, monkeypatch):
    """报告不得含任何绝对路径（否则双跑逐项一致无从谈起，M4 DoD ④）。

    判据不能只查"本测试的 tmp_path"——注入变异（在报告里拼 `os.getcwd()` 等）时
    tmp_path 根本不出现，弱判据会放行。故查**绝对路径的形态特征**：盘符前缀、
    仓库根、以及本层临时目录名（`picrecall-rule-`）。
    """
    import re

    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        result = bench.run_rule_probes(conn)
    finally:
        conn.close()
    blob = json.dumps(result, ensure_ascii=False)
    assert str(tmp_path) not in blob, "规则层报告泄漏了本测试临时目录"
    assert "picrecall-rule-" not in blob, "规则层报告泄漏了本层临时目录名"
    # 形态特征：Windows 盘符前缀（形如「字母 + 冒号 + 斜杠」）与仓库根路径
    assert re.search(r"[A-Za-z]:[\\/]", blob) is None, "规则层报告泄漏了盘符绝对路径"
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert repo_root not in blob, "规则层报告泄漏了仓库根路径"


# ── ③ 规则层可证伪探活（注入机制破坏 → 必红）─────────────────────────────

@pytest.mark.parametrize("defect,expected_red", [
    ("rule_blank_always_true", "single_char_is_detected_and_searchable"),
    ("rule_bound_ignored", "line_bound_predicate_rejects_overflow"),
])
def test_rule_layer_injections_turn_red(tmp_path, monkeypatch, defect, expected_red):
    """注入机制破坏 → 规则层必打红，且**红在预期的对侧探针**（不是随便红一项）。"""
    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        clean = bench.run_rule_probes(conn)
        injected = bench.run_rule_probes(conn, inject_defect=defect)
    finally:
        conn.close()

    assert clean["passed"] is True
    assert injected["passed"] is False, "注入 %s 后规则层未打红（探活空转）" % defect
    red = [p["name"] for p in injected["probes"] if not p["ok"]]
    assert expected_red in red, "注入 %s 未打红对侧探针（红了 %s）" % (defect, red)


def test_rule_layer_clean_run_has_no_red_probe(tmp_path, monkeypatch):
    """未注入时**每一项**探针都必须是绿的（否则"探活"其实是常态红，无意义）。"""
    _stub_rule_engine(monkeypatch)
    conn = _conn(tmp_path)
    try:
        result = bench.run_rule_probes(conn)
    finally:
        conn.close()
    assert result["passed"] is True
    assert [p["name"] for p in result["probes"] if not p["ok"]] == []


def test_rule_layer_degrades_when_ocr_unavailable(tmp_path, monkeypatch):
    """OCR 引擎不可用时：**只降级 OCR 类探针**，索引/检索侧探针照跑并如实标注。

    这是"依赖缺失不得让整层失能"的机制：索引/检索侧端点（坏图、空文件夹、无命中查询）
    不依赖 OCR 引擎，必须仍然给出结论；OCR 类探针标 `available=False` 并在
    `unavailable` 里具名登记——**不冒充已覆盖**。
    """
    def boom():
        raise ocr.MissingDependency("模拟：OCR 引擎不可用")

    monkeypatch.setattr(ocr, "load_engine", boom)

    conn = _conn(tmp_path)
    try:
        result = bench.run_rule_probes(conn)
    finally:
        conn.close()

    # 整层仍给出结论（不因 OCR 缺席而崩或全红）
    assert result["available"] is False
    # 非 OCR 类探针照跑且必须绿
    for name in ("line_bound_predicate_rejects_overflow",
                 "corrupt_image_survives_index_and_search_is_empty",
                 "empty_folder_indexes_cleanly_and_search_is_empty",
                 "absent_and_tokenless_queries_return_empty"):
        assert _probe(result, name)["ok"] is True, "%s 在 OCR 缺席时未照跑" % name
    # OCR 类探针显式标不可用，且具名登记（不冒充已覆盖）
    for name in ("blank_image_yields_no_text_line",
                 "single_char_is_detected_and_searchable",
                 "long_text_does_not_crash_and_lines_bounded"):
        p = _probe(result, name)
        assert p["available"] is False, "%s 未标注不可用（冒充已覆盖）" % name
        assert name in result["unavailable"]
    # passed 只统计**可用**的探针 → OCR 缺席不应使整层判红
    assert result["passed"] is True


# ── ④ 分 profile 门槛（D-22）─────────────────────────────────────────────

def test_manifest_declares_thresholds_by_profile(tmp_path):
    """manifest 须下发分 profile 门槛（数据非代码），且 char/simple 各一套。"""
    out = tmp_path / "synth"
    bench.gen_synthetic(str(out), data_dir=DATA_DIR, seed=20261016, count=2)
    with open(str(out / "manifest.json"), "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    tbp = manifest.get("thresholds_by_profile")
    assert isinstance(tbp, dict), "manifest 未声明 thresholds_by_profile"
    assert set(tbp) == {config.PROFILE_CHAR, config.PROFILE_SIMPLE}, tbp
    for prof, thr in tbp.items():
        assert set(thr) >= {"ocr_line_recall", "query_recall"}, (prof, thr)


def test_effective_thresholds_picks_profile_specific_when_declared():
    """声明了 `thresholds_by_profile` → 按 profile 取生效门槛。"""
    thr = dict(config.BENCH_DEFAULT_THRESHOLDS)
    thr["thresholds_by_profile"] = {
        config.PROFILE_CHAR: {"ocr_line_recall": 0.90, "query_recall": 0.90},
        config.PROFILE_SIMPLE: {"ocr_line_recall": 0.90, "query_recall": 0.80},
    }
    char = bench._effective_thresholds(thr, config.PROFILE_CHAR)
    simple = bench._effective_thresholds(thr, config.PROFILE_SIMPLE)
    assert char["query_recall"] == 0.90
    assert simple["query_recall"] == 0.80, "simple 的 profile 专属门槛未生效"
    # 生效门槛是**扁平**口径（不得把嵌套字典混进去，否则消费侧取值会炸）
    assert "thresholds_by_profile" not in char and "thresholds_by_profile" not in simple


def test_effective_thresholds_falls_back_to_unified_when_absent():
    """未声明 `thresholds_by_profile` → 退回统一门槛（**不并存两套默认**，口径唯一）。"""
    unified = {"ocr_line_recall": 0.91, "query_recall": 0.92}
    for prof in (config.PROFILE_CHAR, config.PROFILE_SIMPLE):
        eff = bench._effective_thresholds(dict(unified), prof)
        assert eff == unified, "未声明分 profile 门槛时未退回统一门槛: %s" % eff


def test_run_bench_uses_profile_specific_threshold(tmp_path, monkeypatch):
    """端到端：simple 库跑 bench → 报告里 `effective_thresholds` 是 simple 那一套。

    分词打桩（不依赖 libsimple DLL）——本项守的是**门槛选取**这一机制，
    不是词级切分质量（后者由 `test_segment.py` 的主路径真调用测试守，带 DLL 时跑）。
    """
    from picrecall import simple_tokenizer

    out = tmp_path / "synth"
    bench.gen_synthetic(str(out), data_dir=DATA_DIR, seed=20261016, count=3)
    with open(str(out / "manifest.json"), "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    _stub_rule_engine(monkeypatch)
    # 词级切分打桩：每个 CJK 字独立成 token（足够让 FTS 表可写，门槛选取与切分粒度无关）
    monkeypatch.setattr(simple_tokenizer, "simple_segment",
                        lambda text: " ".join(text) if text.strip() else "")

    def fake_one(engine, path):
        # 按真值返回该图应识别出的行 → 识别率 1.0，把差异留给检索侧门槛
        name = os.path.basename(path)
        if name in _STUB_BY_NAME:
            return [{"text": t, "conf": 0.99} for t in _STUB_BY_NAME[name]], 0.99
        item = next(i for i in manifest["images"] if i["file"] == name)
        return [{"text": t, "conf": 0.99} for t in item["lines"]], 0.99

    monkeypatch.setattr(ocr, "ocr_one", fake_one)

    conn = db.connect(str(tmp_path / "b.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(out)))
        db.set_meta(conn, "tokenizer_profile", config.PROFILE_SIMPLE)
        ocr.ocr_pending(conn, profile=config.PROFILE_SIMPLE)
        report = bench.run_bench(conn, data_dir=str(out))
    finally:
        conn.close()

    assert report["profile"] == config.PROFILE_SIMPLE
    assert report["effective_thresholds"]["query_recall"] == \
        config.BENCH_THRESHOLDS_BY_PROFILE[config.PROFILE_SIMPLE]["query_recall"]
    # 对照：char 库的同字段必须是 char 那一套（两 profile 的口径确有差别）
    assert config.BENCH_THRESHOLDS_BY_PROFILE[config.PROFILE_SIMPLE]["query_recall"] != \
        config.BENCH_THRESHOLDS_BY_PROFILE[config.PROFILE_CHAR]["query_recall"], \
        "两 profile 门槛相同则本断言无区分度（分 profile 门槛退化成统一门槛）"


# ── ⑤ bench run 报告可复跑（M4 DoD ④）───────────────────────────────────

def _bench_once(tmp_path, name, monkeypatch, out):
    _stub_rule_engine(monkeypatch)
    manifest = json.load(open(str(out / "manifest.json"), "r", encoding="utf-8"))
    monkeypatch.setattr(ocr, "load_engine", lambda: object())

    def fake_one(engine, path):
        bn = os.path.basename(path)
        if bn in _STUB_BY_NAME:
            return [{"text": t, "conf": 0.99} for t in _STUB_BY_NAME[bn]], 0.99
        item = next(i for i in manifest["images"] if i["file"] == bn)
        return [{"text": t, "conf": 0.99} for t in item["lines"]], 0.99

    monkeypatch.setattr(ocr, "ocr_one", fake_one)
    conn = db.connect(str(tmp_path / name))
    try:
        index.apply_scan(conn, index.scan_folder(str(out)))
        ocr.ocr_pending(conn)
        return bench.run_bench(conn, data_dir=str(out))
    finally:
        conn.close()


def test_bench_report_is_identical_across_two_runs(tmp_path, monkeypatch):
    """**同库双跑 `bench run` 报告逐项一致**（M3 只锁了 search/dedupe，没锁 bench 报告本身）。

    两个独立库跑同一输入集（内容一致）→ 报告必须逐项相等。报告里一律不含绝对路径
    与时钟（图片名用 basename、规则层用固定标签），故这里可以直接整体比对。
    """
    out = tmp_path / "synth"
    bench.gen_synthetic(str(out), data_dir=DATA_DIR, seed=20261016, count=4)

    first = _bench_once(tmp_path, "one.db", monkeypatch, out)
    second = _bench_once(tmp_path, "two.db", monkeypatch, out)

    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == \
        json.dumps(second, ensure_ascii=False, sort_keys=True), \
        "同库双跑 bench 报告不一致（含时钟/路径或非确定性排序）"
    # 报告本身不得泄漏绝对路径（否则"逐项一致"是偶然）
    assert str(tmp_path) not in json.dumps(first, ensure_ascii=False)


def test_bench_report_exposes_both_layers(tmp_path, monkeypatch):
    """报告须**单列**规则驱动层一节（M4 DoD ⑤ 的可见性要求）。"""
    out = tmp_path / "synth"
    bench.gen_synthetic(str(out), data_dir=DATA_DIR, seed=20261016, count=3)
    report = _bench_once(tmp_path, "one.db", monkeypatch, out)
    assert "rules" in report and report["rules"]["probes"], "报告缺规则驱动层一节"
    assert report["rules"]["passed"] is True
    names = {p["name"] for p in report["rules"]["probes"]}
    # 四类端点都在（空白/单字符/超长/坏图/空文件夹/无命中查询）
    for expect in ("blank_image_yields_no_text_line",
                   "single_char_is_detected_and_searchable",
                   "long_text_does_not_crash_and_lines_bounded",
                   "corrupt_image_survives_index_and_search_is_empty",
                   "empty_folder_indexes_cleanly_and_search_is_empty",
                   "absent_and_tokenless_queries_return_empty"):
        assert expect in names, "规则层缺探针 %s" % expect


def test_bench_run_cli_reports_rule_layer_and_exit_ok(tmp_path, monkeypatch, capsys):
    """CLI 形态：规则层绿 → 报告含"规则驱动层"一节，exit 0。"""
    from picrecall import cli

    out = tmp_path / "synth"
    bench.gen_synthetic(str(out), data_dir=DATA_DIR, seed=20261016, count=3)
    manifest = json.load(open(str(out / "manifest.json"), "r", encoding="utf-8"))
    _stub_rule_engine(monkeypatch)
    monkeypatch.setattr(ocr, "load_engine", lambda: object())

    def fake_one(engine, path):
        bn = os.path.basename(path)
        if bn in _STUB_BY_NAME:
            return [{"text": t, "conf": 0.99} for t in _STUB_BY_NAME[bn]], 0.99
        item = next(i for i in manifest["images"] if i["file"] == bn)
        return [{"text": t, "conf": 0.99} for t in item["lines"]], 0.99

    monkeypatch.setattr(ocr, "ocr_one", fake_one)

    dbp = str(tmp_path / "cli.db")
    assert cli.main(["index", str(out), "--db", dbp]) == config.EXIT_OK
    assert cli.main(["ocr", "--db", dbp]) == config.EXIT_OK
    capsys.readouterr()
    rc = cli.main(["bench", "run", "--db", dbp, "--data", str(out)])
    out_text = capsys.readouterr().out
    assert rc == config.EXIT_OK
    assert "规则驱动层" in out_text


def test_bench_run_cli_rule_defect_is_exit_1(tmp_path, monkeypatch):
    """CLI 形态：规则层注入机制破坏 → exit 1（可证伪探活打在消费处）。"""
    from picrecall import cli

    out = tmp_path / "synth"
    bench.gen_synthetic(str(out), data_dir=DATA_DIR, seed=20261016, count=3)
    manifest = json.load(open(str(out / "manifest.json"), "r", encoding="utf-8"))
    _stub_rule_engine(monkeypatch)
    monkeypatch.setattr(ocr, "load_engine", lambda: object())

    def fake_one(engine, path):
        bn = os.path.basename(path)
        if bn in _STUB_BY_NAME:
            return [{"text": t, "conf": 0.99} for t in _STUB_BY_NAME[bn]], 0.99
        item = next(i for i in manifest["images"] if i["file"] == bn)
        return [{"text": t, "conf": 0.99} for t in item["lines"]], 0.99

    monkeypatch.setattr(ocr, "ocr_one", fake_one)

    dbp = str(tmp_path / "cli.db")
    cli.main(["index", str(out), "--db", dbp])
    cli.main(["ocr", "--db", dbp])
    rc = cli.main(["bench", "run", "--db", dbp, "--data", str(out),
                   "--inject-defect", "rule_blank_always_true"])
    assert rc == config.EXIT_FINDINGS, "规则层注入缺陷未打红（exit != 1）"
