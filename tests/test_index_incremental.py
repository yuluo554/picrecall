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


# ── M2 边界补测（HANDOFF-M2 §二 3）──────────────────────────────────────────

def test_deleted_then_restored_returns_to_pending_without_duplicate_row(tmp_path):
    """文件先删后回：missing → 再次扫描应回 **pending**，且**不重复插入**行。

    这是"删除只标记"之后的闭环：失效项在同路径重新出现时必须复活（重新识别），
    否则用户"把文件挪回来"后该图永远搜不到（静默失效）。
    """
    folder = tmp_path / "shots"
    folder.mkdir()
    p = _mkpng(folder, "a.png", b"stable-content")
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        row0 = conn.execute("SELECT id, status FROM files").fetchone()
        assert row0["status"] == "pending"

        # 删 → 标记 missing
        os.remove(p)
        r_missing = index.apply_scan(conn, index.scan_folder(str(folder)))
        assert r_missing["missing"] == 1
        assert conn.execute("SELECT status FROM files").fetchone()["status"] == "missing"

        # 写回**同样内容**（新 mtime）→ 复活为 pending，且不算 changed（内容没变）
        with open(p, "wb") as fh:
            fh.write(b"stable-content")
        r_back = index.apply_scan(conn, index.scan_folder(str(folder)))
        assert r_back["added"] == 0, "回迁被当成新文件插入 = 会产生重复行"
        assert r_back["changed"] == 0, "内容未变不应计 changed"
        assert r_back["unchanged"] == 1

        rows = conn.execute("SELECT id, status FROM files").fetchall()
        assert len(rows) == 1, "先删后回产生了重复行"
        assert rows[0]["id"] == row0["id"], "行 id 变了 = 不是同一行在复活"
        assert rows[0]["status"] == "pending", "复活后应重新待识别"
    finally:
        conn.close()


def test_deleted_then_restored_with_same_mtime_uses_fast_path(tmp_path):
    """先删后回且 **mtime 也一致**（备份还原常见）→ 走快速路径也必须回 pending。

    快速路径（size+mtime 均同）不重算 hash，但**不得**让 missing 行永远停留在 missing。
    """
    folder = tmp_path / "shots"
    folder.mkdir()
    p = _mkpng(folder, "a.png", b"payload")
    st = os.stat(p)
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        os.remove(p)
        index.apply_scan(conn, index.scan_folder(str(folder)))
        assert conn.execute("SELECT status FROM files").fetchone()["status"] == "missing"

        with open(p, "wb") as fh:
            fh.write(b"payload")
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))  # 还原 mtime
        result = index.apply_scan(conn, index.scan_folder(str(folder)))
        assert result["unchanged"] == 1
        assert conn.execute("SELECT status FROM files").fetchone()["status"] == "pending"
        assert conn.execute("SELECT COUNT(*) n FROM files").fetchone()["n"] == 1
    finally:
        conn.close()


def test_large_file_hash_is_chunked_and_correct(tmp_path):
    """大文件 hash 分块读边界：跨 1MiB 块的 sha256 必须与整块一致。

    分块实现若在块边界丢字节/重复字节，大图的内容指纹就会错（进而误判"变更"）。
    """
    import hashlib

    chunk = index._HASH_CHUNK
    # 确定性字节（不依赖 random，便于复现）
    blob = bytes((i * 31 + 7) % 256 for i in range(256)) * ((2 * chunk) // 256 + 1)
    p = tmp_path / "big.png"
    p.write_bytes(blob)
    assert p.stat().st_size > 2 * chunk
    assert index.sha256_file(str(p)) == hashlib.sha256(blob).hexdigest()


def test_hash_matches_reference_across_chunk_boundaries(tmp_path):
    """块边界逐档验证：0 / 1 / 块-1 / 块 / 块+1 字节。"""
    import hashlib

    chunk = index._HASH_CHUNK
    for size in (0, 1, chunk - 1, chunk, chunk + 1):
        p = tmp_path / ("f_%d.bin" % size)
        data = bytes((i * 17 + size) % 256 for i in range(size))
        p.write_bytes(data)
        assert index.sha256_file(str(p)) == hashlib.sha256(data).hexdigest(), \
            "分块 hash 在 %d 字节处不一致" % size


def test_index_stores_dimensions_for_real_images(tmp_path):
    """模块 1 契约含"尺寸"，且 K11 分辨率级依赖它——索引必须落库 width/height。"""
    from PIL import Image

    folder = tmp_path / "shots"
    folder.mkdir()
    Image.new("RGB", (123, 45), "white").save(str(folder / "a.png"))
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        row = conn.execute("SELECT width, height FROM files").fetchone()
        assert (row["width"], row["height"]) == (123, 45)
    finally:
        conn.close()


def test_index_survives_unreadable_image(tmp_path):
    """读不出尺寸的坏图不得中断索引（宽容失败 → 尺寸留 NULL）。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    _mkpng(folder, "bad.png", b"\x89PNG\r\n\x1a\n" + bytes(20))  # 非合法 PNG
    _mkpng(folder, "ok.png", b"\x89PNG\r\n\x1a\n" + bytes(20))
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        result = index.apply_scan(conn, index.scan_folder(str(folder)))
        assert result["added"] == 2, "坏图导致索引中断"
        n_null = conn.execute(
            "SELECT COUNT(*) n FROM files WHERE width IS NULL"
        ).fetchone()["n"]
        assert n_null == 2  # 两张都读不出尺寸，但都入库了
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
