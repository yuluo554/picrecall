"""模块 3：FTS5 全文检索 + 中文分词双路径（plan/03 §三、plan/04 §五）。

分词不是"交给 sqlite 的 tokenizer 参数"，而是**索引期与查询期共用的一个纯函数**
segment(text, profile)：CJK 按 profile 切分、ASCII 词保持整体，用空格连接。
FTS5 表固定 tokenize='unicode61'，只吃这个函数的输出。

双路径：
  - char   （兜底，无条件可用）：CJK 逐字切分（unigram），查询词作 phrase 匹配 → 子串语义
  - simple （主路径，需 libsimple DLL）：词级切分，精度更好

阶段 0 实测：sqlite 内建 trigram 对 2 字中文查询（"账单"）返回 0 命中（需 ≥3 字符），
故**不能**用作兜底；逐字切分 + unicode61 实测可用（见 plan/03 §三 证据表）。
"""

import re
import sqlite3

from . import config
from .db import get_meta, write_txn

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")


def _segment_char(text):
    """兜底路径：CJK 逐字切分，ASCII 词整体保留。"""
    out = []
    buf = []
    for ch in text:
        if _CJK.match(ch):
            if buf:
                out.append("".join(buf))
                buf = []
            out.append(ch)
        elif _ASCII_WORD.match(ch):
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    return " ".join(out)


def _segment_simple(text):
    """主路径：libsimple 词级切分（加载失败时调用方回落 char）。"""
    from .simple_tokenizer import simple_segment

    return simple_segment(text)


_SEGMENTERS = {
    config.PROFILE_CHAR: _segment_char,
    config.PROFILE_SIMPLE: _segment_simple,
}


def segment(text, profile=config.PROFILE_CHAR):
    """分词纯函数（索引期与查询期共用同一口径）。"""
    if profile not in _SEGMENTERS:
        raise ValueError("未知分词 profile: %s" % profile)
    return _SEGMENTERS[profile](text)


def make_match_query(query, profile=config.PROFILE_CHAR):
    """把用户查询词转成 FTS5 MATCH 表达式（phrase 匹配，子串语义）。"""
    tokens = segment(query, profile).split()
    if not tokens:
        return None
    escaped = [t.replace('"', '""') for t in tokens]
    return '"%s"' % " ".join(escaped)


def search(conn, query, limit=None, profile=None):
    """检索命中列表。

    排序稳定（K7）：ORDER BY rank, path, line_no —— rank 并列时以路径为决定性 tie-breaker。
    零命中返回 []（合法空结果，exit 0）。
    """
    limit = int(limit or config.DEFAULT_SEARCH_LIMIT)
    db_profile = get_meta(conn, "tokenizer_profile", config.PROFILE_CHAR)
    profile = profile or db_profile
    if profile != db_profile:
        raise ValueError(
            "分词 profile 与索引库不匹配（库=%s，请求=%s）：请重建索引或改用库的 profile"
            % (db_profile, profile)
        )
    match = make_match_query(query, profile)
    if match is None:
        return []

    sql = (
        "SELECT c.file_id AS file_id, c.line_no AS line_no, f.path AS path, "
        "       c.text AS line_text, "
        "       bm25(chunk_fts) AS rank "
        "FROM chunk_fts "
        "JOIN chunk c ON c.id = chunk_fts.rowid "
        "JOIN files f ON f.id = c.file_id "
        "WHERE chunk_fts MATCH ? AND f.status != 'missing' "
        "ORDER BY rank, f.path, c.line_no "
        "LIMIT ?"
    )
    rows = conn.execute(sql, (match, limit)).fetchall()
    terms = _match_terms(query, profile)
    return [
        {
            "file_id": r["file_id"],
            "path": r["path"],
            "line_no": r["line_no"],
            "text": r["line_text"],
            "snippet": make_snippet(r["line_text"], terms),
            "rank": r["rank"],
        }
        for r in rows
    ]


def _match_terms(query, profile):
    """从查询词派生用于高亮/包含判定的原始字面片段（中文整串 + 英文词）。"""
    import re as _re

    terms = []
    for chunk in _re.findall(r"[\u4e00-\u9fff]+", query):
        terms.append(chunk)
    for w in _re.findall(r"[A-Za-z0-9_]{2,}", query):
        terms.append(w)
    return terms


def make_snippet(line_text, terms, width=48):
    """在**原始行文本**上高亮命中片段（不展示切分串）。

    中文按整串高亮（与检索的子串语义一致）；英文按词高亮。
    """
    text = line_text
    spans = []
    for t in terms:
        start = 0
        while True:
            i = text.find(t, start)
            if i < 0:
                break
            spans.append((i, i + len(t)))
            start = i + len(t)
    if not spans:
        return text[:width]
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    out = []
    prev = 0
    for s, e in merged:
        out.append(text[prev:s])
        out.append("[%s]" % text[s:e])
        prev = e
    out.append(text[prev:])
    return "".join(out)


def index_chunks(conn, file_id, lines, profile=config.PROFILE_CHAR):
    """把一个文件的 OCR 行文本写入 chunk（原文）+ FTS（切分串）。

    chunk.text 存**原始行文本**（展示用）；chunk_fts.seg 存 segment() 结果（检索用）。
    """
    with write_txn(conn):
        conn.execute(
            "DELETE FROM chunk_fts WHERE rowid IN (SELECT id FROM chunk WHERE file_id = ?)",
            (file_id,),
        )
        conn.execute("DELETE FROM chunk WHERE file_id = ?", (file_id,))
        for line_no, text in enumerate(lines):
            seg = segment(text, profile)
            if not seg.strip():
                continue
            cur = conn.execute(
                "INSERT INTO chunk(file_id, line_no, text) VALUES (?, ?, ?)",
                (file_id, line_no, text),
            )
            conn.execute(
                "INSERT INTO chunk_fts(rowid, seg) VALUES (?, ?)",
                (cur.lastrowid, seg),
            )


def fts_available(conn):
    """探活：FTS5 是否可用（消费处真调用，不是只看定义）。"""
    try:
        conn.execute("SELECT count(*) FROM chunk_fts")
        return True
    except sqlite3.OperationalError:
        return False
