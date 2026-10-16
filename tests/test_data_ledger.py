"""数据台账生成物测试（M1，plan/05 §六）。

台账纪律：**生成物，禁手改**。三条锁：
  ① 入仓台账与现状一致（--check 绿）；
  ② 手改台账 → --check 必红（否则"生成物"纪律是空话）；
  ③ K15：`tools/` 脚本入口必须调编码守卫（中文控制台）。
"""

import ast
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
LEDGER = os.path.join(REPO_ROOT, "data", "LEDGER.md")
SCRIPT = os.path.join(TOOLS_DIR, "update_data_ledger.py")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _run(args):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, SCRIPT] + args, cwd=REPO_ROOT,
                          capture_output=True, text=True, env=env)


def test_ledger_tool_exists():
    assert os.path.isfile(SCRIPT), "tools/update_data_ledger.py 缺失"


def test_ledger_is_committed():
    """台账必须入 git（否则"数据资产逐份登记"在仓库里无从核验）。"""
    assert os.path.isfile(LEDGER), "data/LEDGER.md 缺失（跑 tools/update_data_ledger.py 生成）"


def test_ledger_check_passes_on_committed_state():
    """入仓台账与现状一致——台账是生成物，不得与数据漂移。"""
    r = _run(["--check"])
    assert r.returncode == 0, "台账核验失败:\n%s\n%s" % (r.stdout, r.stderr)


def test_ledger_check_turns_red_on_manual_edit(tmp_path):
    """手改台账 → --check 必红（锁住"生成物禁手改"）。"""
    backup = _read(LEDGER)
    try:
        with open(LEDGER, "a", encoding="utf-8") as fh:
            fh.write("\n<!-- 手改测试 -->\n")
        r = _run(["--check"])
        assert r.returncode == 1, "手改后台账核验仍通过 = 假门"
        assert "不一致" in (r.stdout + r.stderr)
    finally:
        with open(LEDGER, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(backup)
    assert _run(["--check"]).returncode == 0, "复原后台账应重新一致"


def test_ledger_check_turns_red_when_asset_changes(tmp_path):
    """数据变了而台账未重建 → 必红（台账须随数据走）。"""
    whitelist = os.path.join(REPO_ROOT, "data", "whitelist_texts.txt")
    backup = _read(whitelist)
    try:
        with open(whitelist, "a", encoding="utf-8") as fh:
            fh.write("\n台账漂移探针行\n")
        r = _run(["--check"])
        assert r.returncode == 1, "数据变了台账却不报不一致 = 假门"
    finally:
        with open(whitelist, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(backup)
    assert _run(["--check"]).returncode == 0


def test_ledger_registers_every_asset_with_source_and_license():
    """台账须逐份登记 来源/许可/重建命令/隐私口径（plan/05 §六 要求）。"""
    text = _read(LEDGER)
    for rel in ("data/whitelist_texts.txt", "data/synthetic/manifest.json"):
        assert rel in text, "台账漏登记资产: %s" % rel
    for col in ("来源", "许可", "重建命令", "隐私"):
        assert col in text, "台账缺登记列: %s" % col


def test_tools_scripts_call_encoding_guard():
    """K15：每个 tools/ 脚本入口都要调 _ensure_utf8_stdio（中文控制台守卫）。"""
    offenders = []
    for name in sorted(os.listdir(TOOLS_DIR)):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(_read(os.path.join(TOOLS_DIR, name)))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        if "_ensure_utf8_stdio" not in called and "_ensure_utf8_stdio" not in imported:
            offenders.append(name)
    assert offenders == [], "tools/ 脚本未调编码守卫（K15）: %s" % offenders
