"""索引库 schema 文档纪律（M2，plan/05 §一 + plan/04 §八）。

纪律：schema 的**定义单点**在 `db.SCHEMA_SQL`；`data/schema_notes.md` **只引用不复述**。
若文档里出现第二份可执行的 DDL，两份迟早会漂移，且没有任何测试会红。
"""

import ast
import os
import re

from picrecall import SCHEMA_VERSION, db

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES = os.path.join(REPO_ROOT, "data", "schema_notes.md")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def test_schema_notes_exists():
    assert os.path.isfile(NOTES), "data/schema_notes.md 缺失（plan/05 §一 列为 M2 数据资产）"


def test_schema_notes_references_the_single_source():
    """文档必须显式指向唯一真源（否则读者无从判断哪份为准）。"""
    text = _read(NOTES)
    assert "db.py" in text
    assert "SCHEMA_SQL" in text
    assert "以代码为准" in text


def test_schema_notes_has_no_second_ddl_copy():
    """文档里**不得**出现代码块形式的 DDL 复述（那是第二份 schema 定义）。"""
    text = _read(NOTES)
    offenders = []
    in_fence = False
    for i, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and re.match(r"\s*CREATE\s+(TABLE|VIRTUAL\s+TABLE|INDEX)", line, re.I):
            offenders.append(i)
    assert offenders == [], "schema_notes.md 复述了 DDL（行号 %s）——应只引用 db.SCHEMA_SQL" % offenders


def test_schema_notes_documents_all_status_states():
    """四态语义必须逐条写清（status 是索引状态机的核心契约）。"""
    text = _read(NOTES)
    for state in db.VALID_STATUS:
        assert "`%s`" % state in text, "schema_notes.md 未写明状态: %s" % state


def test_schema_notes_documents_all_tables():
    """每张表都要被讲到（防"加了表没写文档"）。"""
    text = _read(NOTES)
    for table in ("meta", "files", "ocr_text", "chunk", "chunk_fts"):
        assert "`%s`" % table in text, "schema_notes.md 未讲到表: %s" % table


def test_schema_notes_states_version_matches_code():
    """文档里的版本号必须与 `SCHEMA_VERSION` 一致（防"文档写 2、代码是 1"）。"""
    text = _read(NOTES)
    assert SCHEMA_VERSION in text, "schema_notes.md 未提到当前 schema 版本 %s" % SCHEMA_VERSION


def test_valid_status_matches_code_contract():
    """反向锁：`db.VALID_STATUS` 就是四态，不得悄悄增删。"""
    assert set(db.VALID_STATUS) == {"pending", "indexed", "ocr_failed", "missing"}


def test_schema_sql_is_single_point_in_db_module():
    """全包内只有 `db.py` 定义 `SCHEMA_SQL`（防第二份 DDL 常量）。"""
    src_dir = os.path.join(REPO_ROOT, "src", "picrecall")
    offenders = []
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(_read(os.path.join(src_dir, name)))
        for node in tree.body:
            names = []
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            if "SCHEMA_SQL" in names and name != "db.py":
                offenders.append(name)
    assert offenders == [], "SCHEMA_SQL 在 db.py 之外被二次定义: %s" % offenders
