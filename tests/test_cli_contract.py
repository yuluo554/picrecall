"""CLI 契约测试：退出码四语义（K9）+ 参数校验。

纪律：`1 ≠ 跑挂`——退出码判据是"符合 README/决策记录声明过的契约"，不是"全 0"。
"""

import os
import sys

import pytest

from picrecall import cli, config


def _run(argv, tmp_path=None):
    return cli.main(argv)


def test_no_command_is_usage_error(capsys):
    assert _run([]) == config.EXIT_USAGE
    err = capsys.readouterr()
    assert "usage" in (err.out + err.err).lower()


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as e:
        _run(["--version"])
    assert e.value.code == 0


def test_index_missing_folder_is_usage_error(tmp_path, capsys):
    missing = str(tmp_path / "nope")
    assert _run(["index", missing]) == config.EXIT_USAGE
    captured = capsys.readouterr()
    assert "不是有效文件夹" in captured.err


def test_search_on_missing_db_is_usage_error(tmp_path, capsys):
    db = str(tmp_path / "absent.db")
    assert _run(["search", "账单", "--db", db]) == config.EXIT_USAGE
    captured = capsys.readouterr()
    assert "索引库不存在" in captured.err


def test_search_bad_limit_is_usage_error(tmp_path, capsys):
    # 先造一个合法库，确保错误来自 --limit 校验而非库缺失
    folder = tmp_path / "shots"
    folder.mkdir()
    dbp = str(tmp_path / "x.db")
    assert _run(["index", str(folder), "--db", dbp]) == config.EXIT_OK
    assert _run(["search", "账单", "--db", dbp, "--limit", "0"]) == config.EXIT_USAGE
    captured = capsys.readouterr()
    assert "--limit" in captured.err


def test_bench_without_subcommand_is_usage_error(capsys):
    assert _run(["bench"]) == config.EXIT_USAGE
    captured = capsys.readouterr()
    assert "gen 或 run" in captured.err


def test_dedupe_missing_db_is_usage_error(tmp_path, capsys):
    assert _run(["dedupe", "--db", str(tmp_path / "none.db")]) == config.EXIT_USAGE


def test_ocr_missing_db_is_usage_error(tmp_path, capsys):
    assert _run(["ocr", "--db", str(tmp_path / "none.db")]) == config.EXIT_USAGE


def test_empty_search_returns_zero_exit(tmp_path):
    """零命中 = 合法空结果（exit 0），不是错误。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    dbp = str(tmp_path / "x.db")
    _run(["index", str(folder), "--db", dbp])
    assert _run(["search", "不存在的词", "--db", dbp]) == config.EXIT_OK


def test_missing_dependency_is_exit_3(tmp_path, monkeypatch):
    """依赖缺失走 exit 3 契约（用 import 桩模拟引擎缺席，别等 CI）。

    M4 加固：本项此前隐含依赖"进程内 OCR 引擎缓存为冷"——而 M4 的规则驱动层
    （`run_bench` → `run_rule_probes`）会真加载一次引擎，一旦缓存被暖过，
    import 桩就再也拦不住（实测：全量跑时本项红、单跑时绿）。故显式**清空缓存**，
    使契约判定只取决于 import 通路，与测试执行顺序无关。
    """
    import builtins

    from picrecall import ocr as _ocr

    monkeypatch.setattr(_ocr, "_ENGINE", None)  # 契约判定不得依赖缓存状态（M4 加固）

    folder = tmp_path / "shots"
    folder.mkdir()
    dbp = str(tmp_path / "x.db")
    _run(["index", str(folder), "--db", dbp])
    # 造一个 pending 文件，使 ocr 真正走到引擎加载
    (folder / "a.png").write_bytes(b"not-a-real-png")
    _run(["index", str(folder), "--db", dbp])

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "rapidocr_onnxruntime":
            raise ModuleNotFoundError("No module named 'rapidocr_onnxruntime'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert _run(["ocr", "--db", dbp]) == config.EXIT_MISSING_DEP


def test_json_output_is_machine_readable(tmp_path, capsys):
    import json

    folder = tmp_path / "shots"
    folder.mkdir()
    dbp = str(tmp_path / "x.db")
    assert _run(["index", str(folder), "--db", dbp, "--json"]) == config.EXIT_OK
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["db"] == os.path.abspath(dbp)
    assert "scan" in payload


# ── M2：bench gen --dupes 契约 ───────────────────────────────────────────────

def test_bench_gen_dupes_creates_manifest(tmp_path):
    """`--dupes` 产出族 manifest（exit 0），且**不**创建主集目录。"""
    import json
    import os

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    out = tmp_path / "dupes"
    assert _run(["bench", "gen", "--dupes", "--data", data_dir, "--out", str(out)]) == config.EXIT_OK
    with open(str(out / "manifest.json"), "r", encoding="utf-8") as fh:
        m = json.load(fh)
    assert m["schema"] == "picrecall-dupes/1"
    assert m["family_count"] >= 1
    assert len(m["images"]) == m["family_count"] * m["members_per_family"]


def test_bench_gen_dupes_conflicts_with_check(tmp_path, capsys):
    """`--dupes --check` 组合是用法错误——不得**静默忽略**用户给的旗标。"""
    import os

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    out = tmp_path / "dupes"
    assert _run(["bench", "gen", "--dupes", "--check", "--data", data_dir,
                 "--out", str(out)]) == config.EXIT_USAGE
    captured = capsys.readouterr()
    assert "--dupes" in captured.err and "--check" in captured.err


def test_bench_gen_dupes_is_deterministic(tmp_path):
    """同 seed 双跑 → manifest 逐字节一致（K13）。"""
    import os

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    a, b = tmp_path / "a", tmp_path / "b"
    assert _run(["bench", "gen", "--dupes", "--data", data_dir, "--out", str(a)]) == config.EXIT_OK
    assert _run(["bench", "gen", "--dupes", "--data", data_dir, "--out", str(b)]) == config.EXIT_OK
    with open(str(a / "manifest.json"), "rb") as fh:
        first = fh.read()
    with open(str(b / "manifest.json"), "rb") as fh:
        second = fh.read()
    assert first == second


# ── M5：默认数据目录与"照抄 README 能跑"（K9 契约 + 交付面）──────────────────

def _seed_data_dir(tmp_path):
    """造一个最小可用数据目录（只要白名单，`bench gen` 就够用）。"""
    import shutil

    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    shutil.copy(os.path.join(src, "whitelist_texts.txt"),
                str(data_dir / "whitelist_texts.txt"))
    return str(data_dir)


def test_bench_gen_without_data_and_out_uses_default_data_dir(tmp_path, monkeypatch):
    """README §其它命令 里 `bench gen --count 60` 这种**不传 --data/--out** 的形态：
    必须落到默认数据目录，而不是因为 `args.data is None` 裸崩。

    M5 实测缺陷：`cmd_bench_gen` 直接把 `args.data` 传下去，`os.path.join(None, "synthetic")`
    抛裸 `TypeError` → **traceback + exit 1**（并非声明的任何语义）。README 的三条
    `bench gen`（`--count 60` / `--check` / `--dupes`）全都命中，属交付面硬伤。
    """
    from picrecall import bench

    data_dir = _seed_data_dir(tmp_path)
    monkeypatch.setattr(bench, "default_data_dir", lambda: data_dir)

    assert _run(["bench", "gen", "--count", "2"]) == config.EXIT_OK
    out = tmp_path / "data" / "synthetic"
    assert (out / "manifest.json").is_file()
    assert len(list(out.glob("*.png"))) == 2


def test_bench_gen_check_without_data_and_out_uses_default_data_dir(tmp_path, monkeypatch):
    """`bench gen --check` 同形（README §其它命令 第二条）。"""
    from picrecall import bench

    data_dir = _seed_data_dir(tmp_path)
    monkeypatch.setattr(bench, "default_data_dir", lambda: data_dir)

    assert _run(["bench", "gen", "--count", "2"]) == config.EXIT_OK
    assert _run(["bench", "gen", "--check", "--count", "2"]) == config.EXIT_OK


def test_bench_gen_dupes_without_data_and_out_uses_default_data_dir(tmp_path, monkeypatch):
    """`bench gen --dupes` 同形（README §其它命令 第三条）。"""
    import json

    from picrecall import bench

    data_dir = _seed_data_dir(tmp_path)
    monkeypatch.setattr(bench, "default_data_dir", lambda: data_dir)

    assert _run(["bench", "gen", "--dupes", "--count", "2"]) == config.EXIT_OK
    with open(str(tmp_path / "data" / "synthetic_dupes" / "manifest.json"),
              "r", encoding="utf-8") as fh:
        assert json.load(fh)["schema"] == "picrecall-dupes/1"


def test_bench_gen_absent_default_data_dir_is_exit_2_with_actionable_message(
        tmp_path, monkeypatch, capsys):
    """默认数据目录落空（非可编辑安装的形态）→ exit 2，且消息要能照做。

    M0 登记的已知缺口在此收口：与其让下游报一个指向 site-packages 的莫名路径，
    不如在解析处就说清"传 --data"。
    """
    from picrecall import bench

    monkeypatch.setattr(bench, "default_data_dir", lambda: str(tmp_path / "absent"))

    assert _run(["bench", "gen", "--count", "2"]) == config.EXIT_USAGE
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "数据目录不存在" in combined
    assert "--data" in combined
    assert "Traceback" not in combined


def test_bench_run_absent_data_dir_is_exit_2_not_traceback(tmp_path, monkeypatch, capsys):
    """`bench run` 的数据目录/manifest 缺席同样是用法错误（exit 2），不得裸抛。"""
    from picrecall import bench

    folder = tmp_path / "shots"
    folder.mkdir()
    dbp = str(tmp_path / "x.db")
    assert _run(["index", str(folder), "--db", dbp]) == config.EXIT_OK

    monkeypatch.setattr(bench, "default_data_dir", lambda: str(tmp_path / "absent"))
    assert _run(["bench", "run", "--db", dbp]) == config.EXIT_USAGE
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "数据目录不存在" in combined
    assert "Traceback" not in combined
