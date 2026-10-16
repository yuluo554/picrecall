"""回归测试：M0 端到端实测暴露的三处缺陷（防回退）。

① 检索展示必须是**原始行文本**（曾误把切分串当展示文本）；
② 路径展示保留原始大小写（曾误用 normcase 归一后入库，Windows 下路径被小写化）；
③ 合成图渲染宽度必须**容得下文本**（曾在固定 520px 下裁掉长文本，
   而 manifest 仍声明"这行渲染过"→ 真值是假的）。
"""

import json
import os

from picrecall import bench, config, db, index, search


def _png(folder, name, payload=b"x"):
    p = folder / name
    p.write_bytes(payload)
    return str(p)


def test_search_shows_original_text_not_segmented(tmp_path):
    """展示文本必须是原文（含空格与标点），不是逐字切分串。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    _png(folder, "a.png")
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        fid = conn.execute("SELECT id FROM files").fetchone()["id"]
        search.index_chunks(conn, fid, ["本月账单已生成"], config.PROFILE_CHAR)
        hits = search.search(conn, "账单")
        assert len(hits) == 1
        assert hits[0]["text"] == "本月账单已生成"          # 原文
        assert "本 月" not in hits[0]["snippet"]            # 不是切分串
        assert "[账单]" in hits[0]["snippet"]               # 高亮在原文上
    finally:
        conn.close()


def test_stored_path_keeps_original_case(tmp_path):
    """路径展示保留原始大小写（Windows normcase 会小写化，不得用于存储）。"""
    folder = tmp_path / "Shots"
    folder.mkdir()
    _png(folder, "A.png")
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        stored = conn.execute("SELECT path FROM files").fetchone()["path"]
        assert stored.endswith("A.png"), "文件名大小写被改写: %s" % stored
        assert os.path.basename(os.path.dirname(stored)) == "Shots"
    finally:
        conn.close()


def test_path_key_matching_is_case_insensitive(tmp_path):
    """匹配键大小写不敏感：同一文件不同大小写路径不得重复入库。"""
    folder = tmp_path / "shots"
    folder.mkdir()
    _png(folder, "a.png")
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        entries = index.scan_folder(str(folder))
        index.apply_scan(conn, entries)
        variant = [dict(entries[0])]
        variant[0]["path"] = entries[0]["path"].replace("shots", "Shots")
        result = index.apply_scan(conn, variant)
        assert result["added"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"] == 1
    finally:
        conn.close()


def test_synthetic_render_never_clips_text(tmp_path):
    """渲染宽度必须容得下最长行——否则 manifest 真值失真。"""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    out = tmp_path / "synth"
    manifest_path = bench.gen_synthetic(str(out), data_dir=data_dir, seed=7, count=12)

    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    from PIL import Image

    for item in manifest["images"]:
        path = os.path.join(str(out), item["file"])
        with Image.open(path) as im:
            width = im.size[0]
        font = bench._find_font(item["layout"]["font_size"])
        probe_img = Image.new("RGB", (8, 8))
        from PIL import ImageDraw

        draw = ImageDraw.Draw(probe_img)
        widest = max(bench._text_width(draw, line, font) for line in item["lines"])
        assert width >= widest, "%s 画布 %d 装不下最长行 %d" % (item["file"], width, widest)


def test_check_derives_seed_and_count_from_manifest(tmp_path):
    """`--check` 不带 seed/count 时须自派生，否则产生假漂移。"""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    out = tmp_path / "synth"
    bench.gen_synthetic(str(out), data_dir=data_dir, seed=99, count=6)
    result = bench.check_generated(str(out), data_dir=data_dir)   # 不传 seed/count
    assert result["ok"] is True, result


def test_manifest_has_no_observed_fields(tmp_path):
    """K14：manifest 只存输入与期望，不得含观测字段。"""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    out = tmp_path / "synth"
    mp = bench.gen_synthetic(str(out), data_dir=data_dir, count=3)
    with open(mp, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    forbidden = {"observed", "recognized", "hit_rate", "detected", "recall", "mean_conf"}
    for item in manifest["images"]:
        assert not (forbidden & set(item.keys())), "manifest 混入观测字段: %s" % (forbidden & set(item.keys()))
