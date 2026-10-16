"""模块 1：图片导入与增量索引（plan/04 §三）。

输入：用户指定的本地截图文件夹（递归扫描 png/jpg/jpeg/bmp/webp）。
输出：SQLite 索引库记录 路径/hash/mtime/尺寸/索引状态。

纪律：
  - 变更检测以 文件 hash + mtime 双重比对（K2）；
  - 索引内容与文件 hash 绑定，重跑一致；
  - 删除文件只标记失效（status=missing），不动用户文件（K3）；
  - 本模块对用户文件零写操作。
"""

import hashlib
import os
import time

from . import config
from .db import write_txn

_HASH_CHUNK = 1 << 20  # 1MiB


def _norm_path(path):
    """存储路径：绝对路径（保留原始大小写，便于展示）。"""
    return os.path.abspath(path)


def _path_key(path):
    """匹配键：平台大小写归一（Windows 大小写不敏感），仅用于比对，不用于展示。"""
    return os.path.normcase(os.path.abspath(path))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(_HASH_CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def scan_folder(folder, exts=None):
    """递归扫描文件夹，返回确定性排序的文件条目列表。

    返回 [{"path": 归一绝对路径, "size": int, "mtime_ns": int}, ...]
    """
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise NotADirectoryError("不是有效文件夹: %s" % folder)
    exts = {("." + e).lower() for e in (exts or config.SUPPORTED_EXTS)}
    out = []
    for root, dirs, files in os.walk(folder):
        dirs.sort()   # 遍历顺序确定化
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext not in exts:
                continue
            full = _norm_path(os.path.join(root, name))
            try:
                st = os.stat(full)
            except OSError:
                continue
            out.append({"path": full, "size": int(st.st_size), "mtime_ns": int(st.st_mtime_ns)})
    out.sort(key=lambda e: e["path"])  # 决定性排序（K 纪律：禁依赖 os.walk 顺序）
    return out


def apply_scan(conn, entries, now_ns=None):
    """把扫描结果落进索引库，返回变更统计。

    变更判定（K2）：
      - 新路径                                  → status=pending（待 OCR）
      - 同路径且 size+mtime_ns 相同             → 跳过（快速路径，不重算 hash）
      - size/mtime 变 → 重算 sha256：
            hash 同  → unchanged（只更新 mtime_ns/last_seen_ns）
            hash 异  → status=pending（内容变更，需重识别）
      - 库中有、本次未见                        → status=missing（只标记，不删行）
    """
    if now_ns is None:
        now_ns = time.time_ns()

    existing = {
        _path_key(row["path"]): dict(row)
        for row in conn.execute(
            "SELECT id, path, size, mtime_ns, file_hash, status FROM files"
        )
    }

    added = changed = unchanged = 0
    seen_keys = set()

    with write_txn(conn):
        for e in entries:
            path = e["path"]
            key = _path_key(path)
            seen_keys.add(key)
            row = existing.get(key)
            if row is None:
                # 新文件：立即记录内容 hash（题目文档要求索引记录文件 hash），
                # 否则后续"仅触摸"会被误判成内容变更。
                conn.execute(
                    "INSERT INTO files(path, size, mtime_ns, file_hash, status, "
                    "first_seen_ns, last_seen_ns) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                    (path, e["size"], e["mtime_ns"], sha256_file(path), now_ns, now_ns),
                )
                added += 1
                continue

            if row["size"] == e["size"] and row["mtime_ns"] == e["mtime_ns"]:
                # 快速路径：元数据未变，不重算 hash
                conn.execute(
                    "UPDATE files SET last_seen_ns = ?, status = CASE "
                    "WHEN status = 'missing' THEN 'pending' ELSE status END WHERE id = ?",
                    (now_ns, row["id"]),
                )
                unchanged += 1
                continue

            # 元数据变了 → 重算内容 hash 决定是"变更"还是"仅触摸"
            new_hash = sha256_file(path)
            if row["file_hash"] == new_hash:
                conn.execute(
                    "UPDATE files SET size = ?, mtime_ns = ?, last_seen_ns = ?, "
                    "status = CASE WHEN status = 'missing' THEN 'pending' ELSE status END "
                    "WHERE id = ?",
                    (e["size"], e["mtime_ns"], now_ns, row["id"]),
                )
                unchanged += 1
            else:
                conn.execute(
                    "UPDATE files SET size = ?, mtime_ns = ?, file_hash = ?, "
                    "status = 'pending', last_seen_ns = ?, ocr_error = NULL WHERE id = ?",
                    (e["size"], e["mtime_ns"], new_hash, now_ns, row["id"]),
                )
                changed += 1

        # 本次未见 → 只标记失效（K3：不删行、不动文件）
        missing = 0
        for key, row in existing.items():
            if key in seen_keys:
                continue
            if row["status"] != "missing":
                conn.execute("UPDATE files SET status = 'missing' WHERE id = ?", (row["id"],))
            missing += 1

    return {"added": added, "changed": changed, "unchanged": unchanged, "missing": missing}


def index_stats(conn):
    """索引库状态速览。"""
    by_status = {
        row["status"]: row["n"]
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM files GROUP BY status")
    }
    total = conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"]
    ocr_done = conn.execute("SELECT COUNT(*) AS n FROM ocr_text").fetchone()["n"]
    return {"total_files": total, "by_status": by_status, "ocr_done": ocr_done}
