"""模块 4 只读纪律测试（K10/K11）：绝不删除用户文件 + 组外样本不变。

变异验证：若在 dedupe 里注入删除调用，本文件的断言必须变红。
"""

from picrecall import db, dedupe, index


def _mkpng(folder, name, size=16):
    p = folder / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(size))
    return str(p)


def test_dedupe_has_no_deletion_path():
    """静态守门（AST）：模块里不得出现删除/改名用户文件的调用。

    用 AST + import 别名解析，而非子串扫描——子串扫描可被
    `import os as _o; _o.remove(...)` 这类别名规避（变异验证已证）。
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(dedupe))
    # 建立"模块/别名 → 危险函数名"的解析
    aliases = {}          # 本地名 → 真实模块名
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name.split(".")[0]] = a.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for a in node.names:
                    aliases[a.asname or a.name] = "%s.%s" % (node.module, a.name)

    dangerous = {
        "os.remove", "os.unlink", "os.rename", "os.replace", "os.rmdir",
        "shutil.rmtree", "shutil.move", "pathlib.Path.unlink",
    }
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if not isinstance(func.value, ast.Name):
            continue
        local = func.value.id
        real = aliases.get(local, local)
        resolved = "%s.%s" % (real, func.attr)
        if resolved in dangerous or "%s.%s" % (local, func.attr) in dangerous:
            hits.append(resolved)
    assert hits == [], "dedupe 出现破坏性调用: %s" % sorted(set(hits))


def test_dedupe_never_touches_user_files(tmp_path):
    folder = tmp_path / "shots"
    folder.mkdir()
    for name in ("a.png", "b.png", "c.png"):
        _mkpng(folder, name)
    before = sorted(p.name for p in folder.iterdir())
    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        groups = dedupe.phash_groups(conn)
        out = tmp_path / "suggest.csv"
        if groups:
            dedupe.write_keep_suggestions(groups, str(out))
    finally:
        conn.close()
    after = sorted(p.name for p in folder.iterdir())
    assert before == after, "dedupe 动了用户文件"


def test_dedupe_never_touches_user_files_with_real_groups(tmp_path):
    """只读纪律在**真有组**时仍成立（M2 补）。

    上面的测试走的是 0 组场景（合成版式各异），只证明了"空手而过时不动文件"。
    本测试用 `bench.gen_dupes()` 造出**必然出组**的近似重复族，再断言：
      ① 调用前后用户文件夹**文件集合 + size + mtime_ns** 逐一不变；
      ② 确实分出了组（否则本测试又退化成"0 组"场景，失去意义）；
      ③ 唯一写盘动作是建议清单，且该清单落在用户文件夹**之外**。
    """
    import os

    from picrecall import bench

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    folder = tmp_path / "shots"
    bench.gen_dupes(str(folder), data_dir=data_dir, count=3)

    def snapshot():
        return {
            p.name: (p.stat().st_size, p.stat().st_mtime_ns)
            for p in folder.iterdir()
        }

    before = snapshot()
    assert len(before) == 10  # 3 族 × 3 成员 + manifest.json

    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        groups = dedupe.phash_groups(conn)
        # ② 真有组——否则本测试没测到"有组时的只读性"
        assert len(groups) >= 1, "样例未出组，只读断言不具针对性"
        out = tmp_path / "suggest.csv"   # 落在 shots/ 之外
        dedupe.write_keep_suggestions(groups, str(out))
        assert os.path.isfile(out)
    finally:
        conn.close()

    after = snapshot()
    assert before == after, "有组场景下 dedupe 改了用户文件（集合/size/mtime 有变）"
    # ③ 建议清单不得写进用户文件夹
    assert not (folder / "suggest.csv").exists()


def test_suggestion_priority_resolution_then_size_then_mtime(tmp_path):
    """K11：分辨率 → 大小 → mtime → 路径。"""
    members = [
        {"path": "/x/small.png", "size": 100, "width": 100, "height": 100,
         "mtime_ns": 1, "hash": None},
        {"path": "/x/big.png", "size": 50, "width": 800, "height": 600,
         "mtime_ns": 1, "hash": None},
    ]
    rep = dedupe.choose_representative(members)
    assert rep["path"] == "/x/big.png"   # 分辨率优先，即便文件更小


def test_suggestion_rows_mark_one_keep_rest_redundant():
    groups = [{
        "group_id": 1,
        "representative": {"path": "/x/a.png", "hash": None},
        "members": [
            {"path": "/x/a.png", "phash": "h1", "file_size": 10, "width": 100,
             "height": 100, "mtime_ns": 2, "max_distance_to_rep": 0},
            {"path": "/x/b.png", "phash": "h2", "file_size": 9, "width": 100,
             "height": 100, "mtime_ns": 1, "max_distance_to_rep": 3},
        ],
    }]
    rows = dedupe.build_suggestion_rows(groups)
    kinds = {r[1] for r in rows}
    assert kinds == {"keep", "redundant"}
    assert sum(1 for r in rows if r[1] == "keep") == 1


def test_group_outside_members_are_not_included(tmp_path):
    """组外样本不变：与任何图都不相似的图不得进任何组。

    注意：纯色图（无论黑白）的 pHash 都近乎全零，故必须用**带纹理**的图做"不同"样本，
    否则测的是"纯色图互相相似"，与"组外样本"无关。
    """
    from PIL import Image

    folder = tmp_path / "shots"
    folder.mkdir()

    def textured(name, seed_shift):
        im = Image.new("RGB", (64, 64))
        px = im.load()
        for y in range(64):
            for x in range(64):
                v = ((x * 7 + y * 13 + seed_shift) % 2) * 255
                px[x, y] = (v, v, v)
        im.save(folder / name)

    textured("a.png", 0)
    textured("b.png", 0)     # 与 a 完全相同
    textured("z.png", 1)     # 反相纹理 → pHash 明显不同

    conn = db.connect(str(tmp_path / "i.db"))
    try:
        index.apply_scan(conn, index.scan_folder(str(folder)))
        groups = dedupe.phash_groups(conn, threshold=4)
    finally:
        conn.close()
    grouped = {m["path"] for g in groups for m in g["members"]}
    assert any(p.endswith("a.png") for p in grouped) is True
    assert any(p.endswith("z.png") for p in grouped) is False
