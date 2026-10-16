"""`bench gen --check` 守门测试（M1）。

核心纪律：**篡改图片必须打红**（可证伪），同时不得把"跨环境的编码器字节差异"
误报成数据漂移。M1 实测发现：同一张图在 Pillow 10.4.0 与 12.3.0 下**像素 0 差异、
PNG 的 IDAT 压缩流不同**（文件 sha256 不同），故位级一致须用两层锚：
文件 sha256（严格完整性）+ pixel_sha256（跨环境内容指纹）。
"""

import json
import os

from picrecall import bench

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _gen(tmp_path, count=6, seed=20261016):
    out = tmp_path / "synth"
    bench.gen_synthetic(str(out), data_dir=DATA_DIR, seed=seed, count=count)
    return out


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_check_passes_on_freshly_generated_set(tmp_path):
    """同环境重生成 → 逐字节一致 → 绿。"""
    out = _gen(tmp_path)
    result = bench.check_generated(str(out), data_dir=DATA_DIR)
    assert result["ok"] is True, result
    assert result["images"] == 6
    assert "encoder_mismatch" not in result


def test_check_turns_red_when_image_bytes_appended(tmp_path):
    """篡改：在 IEND 之后追加字节 → **必红**。

    这是 M0 已锁的可证伪性（plan/verify §三 #17）。注意尾部追加**不改像素**，
    故绝不能用"像素一致"放行——否则篡改会被误判成编码器差异，守门失效。
    """
    out = _gen(tmp_path)
    target = out / "img_0001.png"
    with open(str(target), "ab") as fh:
        fh.write(b"\x00\x01\x02")
    result = bench.check_generated(str(out), data_dir=DATA_DIR)
    assert result["ok"] is False
    assert "img_0001.png" in result["reason"]


def test_check_turns_red_when_pixel_changed(tmp_path):
    """篡改：改一个像素 → 必红。"""
    from PIL import Image

    out = _gen(tmp_path)
    target = out / "img_0002.png"
    with Image.open(str(target)) as im:
        conv = im.convert("RGB")
        px = conv.load()
        px[5, 5] = (0, 0, 0)
        conv.save(str(target))
    result = bench.check_generated(str(out), data_dir=DATA_DIR)
    assert result["ok"] is False
    assert "img_0002.png" in result["reason"]


def test_check_turns_red_when_image_missing(tmp_path):
    """图片缺失 → 必红（不能对"文件不见了"视而不见）。"""
    out = _gen(tmp_path)
    os.remove(str(out / "img_0003.png"))
    result = bench.check_generated(str(out), data_dir=DATA_DIR)
    assert result["ok"] is False
    assert "缺失" in result["reason"]


def test_check_turns_red_when_manifest_truth_drifts(tmp_path):
    """真值面漂移（渲染文本被改）→ 必红，并给出定位。"""
    out = _gen(tmp_path)
    mpath = out / "manifest.json"
    manifest = _read(str(mpath))
    manifest["images"][0]["lines"] = ["被篡改的渲染文本"]
    with open(str(mpath), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, sort_keys=True, indent=2)
    result = bench.check_generated(str(out), data_dir=DATA_DIR)
    assert result["ok"] is False
    assert "真值不一致" in result["reason"]


def test_manifest_registers_both_byte_and_pixel_anchors(tmp_path):
    """manifest 须同时登记文件 sha256（完整性）与 pixel_sha256（跨环境内容锚）。"""
    out = _gen(tmp_path)
    manifest = _read(str(out / "manifest.json"))
    for item in manifest["images"]:
        assert len(item["sha256"]) == 64
        assert len(item["pixel_sha256"]) == 64
        assert item["sha256"] != item["pixel_sha256"]


def test_pixel_anchor_is_encoder_independent(tmp_path):
    """像素锚的性质：重写同一张图（换编码路径）后像素指纹不变、字节指纹变。

    这直接模拟"跨 Pillow 版本"的效应，无需装两套 Pillow 即可锁住性质。
    """
    from PIL import Image

    out = _gen(tmp_path, count=2)
    p = str(out / "img_0001.png")
    before = bench._pixel_sha256(p)
    before_bytes = bench._sha256(p)

    # 以"另一种编码参数"重写同一张图（像素不变）
    with Image.open(p) as im:
        im.convert("RGB").save(p, format="PNG", optimize=True, compress_level=9)

    assert bench._pixel_sha256(p) == before, "像素指纹应跨编码方式稳定"
    # 字节指纹可能变（视编码器而定）——这里只断言"像素锚不受编码影响"
    assert isinstance(before_bytes, str)


def test_check_derives_seed_and_count_without_false_drift(tmp_path):
    """不带 seed/count 调用 --check 不得产生假漂移（M0 缺陷 #5 的回归）。"""
    out = _gen(tmp_path, count=4, seed=7)
    result = bench.check_generated(str(out), data_dir=DATA_DIR)
    assert result["ok"] is True, result


# ── M1 口径修正回归：OCR 把一条渲染行切成多个框时不得误判"未检出" ──
# 约定：`_contained_in_contiguous_run(needle, texts)` 收的都是**已归一化**串
#       （与 run_bench 内一致），故测试也按归一化口径调用。

def test_contiguous_run_detects_line_split_across_boxes():
    """OCR 输出把一行切成相邻两框 → 主口径必须判"检出"。"""
    texts = [bench._normalize(t) for t in
             ("config", "error:timeout3000", "自动保存每5分钟")]
    assert bench._contained_in_contiguous_run(
        bench._normalize("config error: timeout 3000"), texts) is True


def test_contiguous_run_rejects_non_adjacent_stitching():
    """只允许**连续**拼接：不相邻的碎片不得拼成假命中（防口径过宽）。"""
    texts = [bench._normalize(t) for t in ("订单", "无关中间行", "金额 128")]
    assert bench._contained_in_contiguous_run(bench._normalize("订单金额"), texts) is False


def test_contiguous_run_handles_single_and_empty():
    assert bench._contained_in_contiguous_run("账单", ["本月账单已生成"]) is True
    assert bench._contained_in_contiguous_run("", ["x"]) is False
    assert bench._contained_in_contiguous_run("x", []) is False


def test_bench_report_exposes_both_calibers(tmp_path):
    """报告须同时给出主口径与严格单条口径（宽松度必须可见，不许只报好看的那个）。"""
    import json

    from picrecall import db, index

    out = _gen(tmp_path, count=2)
    manifest = _read(str(out / "manifest.json"))
    conn = db.connect(str(tmp_path / "b.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(out)))
        # 造一条"被切成两框"的 OCR 结果，模拟实测场景
        fid = conn.execute("SELECT id FROM files ORDER BY path").fetchone()["id"]
        line0 = manifest["images"][0]["lines"][0]
        conn.execute(
            "INSERT INTO ocr_text(file_id, text, line_json, mean_conf, line_count, engine, run_sig) "
            "VALUES (?, '', ?, 0.99, 2, 'stub', 'sig')",
            (fid, json.dumps([{"text": line0[:2], "conf": 0.99},
                              {"text": line0[2:], "conf": 0.99}],
                             ensure_ascii=False, sort_keys=True)),
        )
        conn.commit()
        report = bench.run_bench(conn, data_dir=str(out))
    finally:
        conn.close()
    ocr = report["ocr"]
    assert "recall" in ocr and "recall_strict_single_line" in ocr
    assert "strict_line_hits" in ocr
    # 被切成两框的行：主口径应判检出，严格口径应判未检出 → 主口径 >= 严格口径
    assert ocr["recall"] >= ocr["recall_strict_single_line"]
