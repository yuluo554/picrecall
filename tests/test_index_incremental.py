"""模块 1 增量索引测试（K2/K3）：重跑一致、双重比对、只读纪律。"""

import os
import time

from picrecall import db, index


def _mkpng(folder, name, payload):
    p = folder / name
    p.write_bytes(payload)
    return str(p)


def test_rerun_is_idempotent(tmp_path):
    folder = tmp_path / "shots"
    folder.mkdir()
    _mkpng(folder, "a.png", b"aaa")
    _mkpng(folder, "b.jpg", b"bbb")
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        entries = index.scan_folder(str(folder))
        first = index.apply_scan(conn, entries)
        assert first["added"] == 2
        second = index.apply_scan(conn, entries)
        assert second == {"added": 0, "changed": 0, "unchanged": 2, "missing": 0}
    finally:
        conn.close()


def test_content_change_marks_pending(tmp_path):
    folder = tmp_path / "shots"
    folder.mkdir()
    p = _mkpng(folder, "a.png", b"aaa")
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        # 改内容（同时改 mtime）
        time.sleep(0.01)
        with open(p, "wb") as fh:
            fh.write(b"changed-content")
        result = index.apply_scan(conn, index.scan_folder(str(folder)))
        assert result["changed"] == 1
        status = conn.execute("SELECT status FROM files").fetchone()["status"]
        assert status == "pending"
    finally:
        conn.close()


def test_touch_only_is_not_a_change(tmp_path):
    """mtime 变但内容 hash 同 → unchanged（双重比对的意义）。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    p = _mkpng(folder, "a.png", b"same")
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        os.utime(p, (time.time() + 100, time.time() + 100))
        result = index.apply_scan(conn, index.scan_folder(str(folder)))
        assert result["unchanged"] == 1
        assert result["changed"] == 0
    finally:
        conn.close()


def test_deleted_file_is_marked_missing_and_row_kept(tmp_path):
    """K3：删除只标记失效，不删行、不动文件。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    _mkpng(folder, "a.png", b"aaa")
    _mkpng(folder, "b.png", b"bbb")
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        os.remove(str(folder / "a.png"))
        result = index.apply_scan(conn, index.scan_folder(str(folder)))
        assert result["missing"] == 1
        rows = conn.execute("SELECT path, status FROM files ORDER BY path").fetchall()
        assert len(rows) == 2                       # 行仍在
        assert [r["status"] for r in rows].count("missing") == 1
    finally:
        conn.close()


def test_user_files_untouched_by_indexing(tmp_path):
    """只读纪律：索引前后用户文件的 size/mtime/存在性不变。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    _mkpng(folder, "a.png", b"payload-1")
    _mkpng(folder, "b.webp", b"payload-2")
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in folder.iterdir()}
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
    finally:
        conn.close()
    after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in folder.iterdir()}
    assert before == after


def test_extension_whitelist_is_enforced(tmp_path):
    folder = tmp_path / "shots"
    folder.mkdir()
    _mkpng(folder, "a.png", b"x")
    _mkpng(folder, "notes.txt", b"x")
    _mkpng(folder, "doc.pdf", b"x")
    entries = index.scan_folder(str(folder))
    assert [os.path.basename(e["path"]) for e in entries] == ["a.png"]


def test_scan_order_is_deterministic(tmp_path):
    folder = tmp_path / "shots"
    folder.mkdir()
    for name in ("c.png", "a.png", "b.jpg"):
        _mkpng(folder, name, name.encode())
    first = [e["path"] for e in index.scan_folder(str(folder))]
    second = [e["path"] for e in index.scan_folder(str(folder))]
    assert first == second == sorted(first)
