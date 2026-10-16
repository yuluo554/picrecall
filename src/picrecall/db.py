"""索引库 schema 与写盘单点（plan/03 §五、plan/04 §一）。

纪律：
  - 建库/迁移只此一处；写操作一律经 write_txn() 上下文（原子事务）。
  - 索引库记录 tokenizer profile 与 schema 版本，供检索侧一致性校验。
  - 本模块只对索引库做读写；对用户文件零操作。
"""

import contextlib
import os
import sqlite3

from . import SCHEMA_VERSION, config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
  id            INTEGER PRIMARY KEY,
  path          TEXT    NOT NULL UNIQUE,
  size          INTEGER NOT NULL,
  mtime_ns      INTEGER NOT NULL,
  width         INTEGER,
  height        INTEGER,
  file_hash     TEXT,
  status        TEXT    NOT NULL,
  ocr_tries     INTEGER NOT NULL DEFAULT 0,
  ocr_error     TEXT,
  first_seen_ns INTEGER NOT NULL,
  last_seen_ns  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ocr_text (
  file_id    INTEGER PRIMARY KEY REFERENCES files(id),
  text       TEXT    NOT NULL,
  line_json  TEXT    NOT NULL,
  mean_conf  REAL    NOT NULL,
  line_count INTEGER NOT NULL,
  engine     TEXT    NOT NULL,
  run_sig    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS chunk (
  id      INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL REFERENCES files(id),
  line_no INTEGER NOT NULL,
  text    TEXT    NOT NULL      -- 原始行文本（展示用，不切分）
);

-- FTS 表独立存放**切分后**文本（seg），与 chunk 的原始文本分开：
-- 展示走 chunk.text，检索走 seg，避免把切分串直接呈现给用户。
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
  seg, tokenize='unicode61'
);

CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_chunk_file ON chunk(file_id);
"""

VALID_STATUS = ("pending", "indexed", "ocr_failed", "missing")


def connect(db_path):
    """打开（必要时创建）索引库并确保 schema 就位。"""
    db_path = os.path.abspath(db_path)
    parent = os.path.dirname(db_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn


def ensure_schema(conn):
    conn.executescript(SCHEMA_SQL)
    _set_meta_default(conn, "schema_version", SCHEMA_VERSION)
    conn.commit()


def _set_meta_default(conn, key, value):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (key, str(value)))


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


@contextlib.contextmanager
def write_txn(conn):
    """写事务单点：正常提交，异常回滚。"""
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def delete_derived_rows(conn, file_id):
    """作废某个文件的**派生结果行**（`ocr_text` / `chunk` / `chunk_fts` + 低置信度计数）。

    只作用于索引库的派生表，**不动** `files` 台账行、更不动用户文件（K3 的"永不删行"
    约束针对台账与用户文件，不针对"随内容失效即作废"的派生缓存）。
    调用方须已在 `write_txn()` 内（本函数不自开事务，避免嵌套提交）。
    """
    conn.execute(
        "DELETE FROM chunk_fts WHERE rowid IN (SELECT id FROM chunk WHERE file_id = ?)",
        (file_id,),
    )
    conn.execute("DELETE FROM chunk WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM ocr_text WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM meta WHERE key = ?", ("low_conf_lines_%d" % file_id,))


def schema_version(conn):
    return get_meta(conn, "schema_version", SCHEMA_VERSION)
