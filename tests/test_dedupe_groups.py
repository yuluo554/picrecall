"""模块 4 端到端"能真出组"真样例（M2）。

M0/M1 的 dedupe 测试只覆盖了两处：**单元级**的手工构造 members（K11 优先级、组外不变），
以及 **0 组**场景下的只读断言。0 组的绿只能证明"没崩"，**不能证明分组逻辑正确**。
本文件补的是：从**真实图片文件**走完 `phash_groups()` 全程，且**必然出组**。

真样例来源：`bench.gen_dupes()` 生成的近似重复族（同文本同版式，仅缩放/编码不同），
实测族内 pHash 距离 ≤6（默认阈值 8）、族间 ≥56，故分组必出组且不误并。

变异验证（见 plan/verify §M2 四）：把 `phash_groups` 的分组条件改成恒 False（不出组）、
或把 `choose_representative` 的优先级顺序改掉，本文件的断言必须变红。
"""

import json
import os

from picrecall import bench, db, dedupe, index

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _gen_dupes(tmp_path, count=3, seed=None):
    out = tmp_path / "dupes"
    bench.gen_dupes(str(out), data_dir=DATA_DIR, seed=seed, count=count)
    return out


def _index(tmp_path, folder):
    conn = db.connect(str(tmp_path / "i.db"))
    index.apply_scan(conn, index.scan_folder(str(folder)))
    return conn


def _manifest(folder):
    with open(os.path.join(str(folder), "manifest.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_dupes_manifest_is_truth_only(tmp_path):
    """K14：族 manifest 只存输入与期望，不得出现观测字段。"""
    out = _gen_dupes(tmp_path, count=2)
    m = _manifest(out)
    assert m["schema"] == bench.DUPES_MANIFEST_SCHEMA
    for item in m["images"]:
        assert set(("lines", "queries", "layout", "family_id", "role")) <= set(item)
        for banned in ("observed", "recognized", "hit_rate", "group_id", "is_representative"):
            assert banned not in item, "族 manifest 混入观测字段: %s" % banned


def test_phash_groups_finds_real_groups_from_image_files(tmp_path):
    """核心：真实图片文件走完 phash_groups 全程 → **出组数 >= 1**。

    这是 HANDOFF-M2 §二 1 指出缺的那一环：0 组实测无法证明"分组逻辑正确"。
    """
    out = _gen_dupes(tmp_path, count=3)
    conn = _index(tmp_path, out)
    try:
        groups = dedupe.phash_groups(conn)
    finally:
        conn.close()

    assert len(groups) >= 1, "近似重复族样例仍未出组——端到端分组未被真正验证"
    # 每族成员数 = 生成器声明的 members_per_family
    expect = _manifest(out)["members_per_family"]
    assert all(len(g["members"]) == expect for g in groups)
    assert sum(len(g["members"]) for g in groups) == _manifest(out)["image_count"]


def test_group_membership_matches_declared_families(tmp_path):
    """分出的组必须与生成器声明的族**一一对应**（既不出错组，也不并族）。"""
    out = _gen_dupes(tmp_path, count=4)
    conn = _index(tmp_path, out)
    try:
        groups = dedupe.phash_groups(conn)
    finally:
        conn.close()

    m = _manifest(out)
    truth = {}
    for item in m["images"]:
        truth[item["family_id"]] = truth.get(item["family_id"], set()) | {item["file"]}

    got = []
    for g in groups:
        got.append({os.path.basename(x["path"]) for x in g["members"]})
    assert sorted(got, key=sorted) == sorted(truth.values(), key=sorted), \
        "分组结果与 manifest 声明的族不一致"


def test_representative_follows_k11_resolution_tier_end_to_end(tmp_path):
    """K11 第①级（分辨率）必须**真的被用上**——端到端可区分。

    M2 实测发现：`apply_scan` 此前**不写** width/height（60/60 为 NULL），
    致 K11 第①级在端到端路径上恒不生效（退化成"只比文件大小"）。本测试锁住修复。

    构造上刻意让 **分辨率最高者 ≠ 文件最大者**（低分辨率成员用 BMP 编码，字节更大），
    故只有"分辨率优先"才会选中 hi_res。
    """
    out = _gen_dupes(tmp_path, count=3)
    conn = _index(tmp_path, out)
    try:
        # 修复验证：尺寸必须已落库
        n_null = conn.execute(
            "SELECT COUNT(*) n FROM files WHERE width IS NULL OR height IS NULL"
        ).fetchone()["n"]
        assert n_null == 0, "索引未写入图片尺寸 → K11 分辨率级在端到端路径上失效"

        groups = dedupe.phash_groups(conn)
        rows = {
            r["path"]: r for r in
            conn.execute("SELECT path, size, width, height FROM files")
        }
    finally:
        conn.close()

    assert groups
    for g in groups:
        members = g["members"]
        # 前提校验：本样例确属"分辨率最大者 ≠ 文件最大者"（否则断言无信息量）
        by_area = max(members, key=lambda m: (m["width"] or 0) * (m["height"] or 0))
        by_size = max(members, key=lambda m: m["file_size"])
        assert by_area["path"] != by_size["path"], \
            "样例未解耦分辨率与大小，断言不具区分度（生成器设计被改动？）"
        # K11 第①级优先 → 代表必须是分辨率最高者，即便它的文件更小
        assert g["representative"]["path"] == by_area["path"], \
            "代表性选择未按 K11 分辨率优先级"


def test_dupes_grouping_is_reproducible_byte_identical(tmp_path):
    """分组结果可复跑：同输入双跑 → 建议清单 CSV 逐字节一致。"""
    out = _gen_dupes(tmp_path, count=3)
    conn = _index(tmp_path, out)
    try:
        g1 = dedupe.phash_groups(conn)
        c1 = str(tmp_path / "a.csv")
        dedupe.write_keep_suggestions(g1, c1)
        g2 = dedupe.phash_groups(conn)
        c2 = str(tmp_path / "b.csv")
        dedupe.write_keep_suggestions(g2, c2)
    finally:
        conn.close()

    with open(c1, "rb") as fh:
        b1 = fh.read()
    with open(c2, "rb") as fh:
        b2 = fh.read()
    assert b1 == b2, "同输入双跑的分组建议清单不一致（分组或写盘不确定）"
    # 结构面：每组恰一条 keep，其余 redundant
    text = b1.decode("utf-8")
    assert text.count(",keep,") == len(g1)
    assert text.count(",redundant,") == sum(len(g["members"]) for g in g1) - len(g1)


def test_threshold_controls_grouping_observably(tmp_path):
    """阈值必须是**真判据**：收紧到 0 后，近似（非同像素）成员应掉出组。

    变异验证：若 `phash_groups` 忽略 threshold 参数，本测试必须红。
    """
    out = _gen_dupes(tmp_path, count=2)
    conn = _index(tmp_path, out)
    try:
        loose = dedupe.phash_groups(conn)
        tight = dedupe.phash_groups(conn, threshold=0)
    finally:
        conn.close()

    assert len(loose) >= 1
    loose_members = sum(len(g["members"]) for g in loose)
    tight_members = sum(len(g["members"]) for g in tight)
    assert tight_members <= loose_members
    # 族内成员是"缩放/编码不同"的近似图，像素不同 → 阈值为 0 时不应再全并入同一组
    assert tight_members < loose_members, "threshold 未参与判据（恒等于默认值？）"
