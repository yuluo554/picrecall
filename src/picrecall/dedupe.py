"""模块 4：重复截图合并建议（plan/04 §六）。

纪律（K10/K11）：
  - **默认只读，绝不自动删除**：本模块没有任何删除/改名/写回用户文件的代码路径；
  - pHash 相似阈值一处定义（config.PHASH_MAX_DISTANCE）；
  - 只输出保留建议清单（CSV），不执行任何动作。
"""

from . import config
from .serialize import write_csv

SUGGESTION_HEADER = (
    "group_id",
    "suggestion",
    "path",
    "phash",
    "file_size",
    "width",
    "height",
    "mtime_ns",
    "max_distance_to_rep",
)


def compute_phash(path, hash_size=None):
    """计算 pHash（确定性）。缺 imagehash/PIL 时抛 ImportError 由调用方契约化。"""
    import imagehash
    from PIL import Image

    hash_size = hash_size or config.PHASH_HASH_SIZE
    with Image.open(path) as im:
        return imagehash.phash(im.convert("RGB"), hash_size=hash_size)


def phash_groups(conn, threshold=None, hash_size=None):
    """对已索引文件做 pHash 相似分组，返回分组列表（只读）。

    分组确定性：单链聚类，成员与组顺序按 path 排序。
    """
    threshold = config.PHASH_MAX_DISTANCE if threshold is None else int(threshold)
    rows = conn.execute(
        "SELECT id, path, size, mtime_ns, width, height FROM files "
        "WHERE status != 'missing' ORDER BY path"
    ).fetchall()

    items = []
    for r in rows:
        try:
            h = compute_phash(r["path"], hash_size=hash_size)
        except Exception:
            continue  # 读不出图的跳过（不中断分组）
        items.append(
            {
                "id": r["id"],
                "path": r["path"],
                "size": r["size"],
                "mtime_ns": r["mtime_ns"],
                "width": r["width"],
                "height": r["height"],
                "hash": h,
            }
        )

    # 单链聚类（确定性：以 path 序为起点，只用距离判据）
    groups = []
    used = set()
    for i, a in enumerate(items):
        if i in used:
            continue
        members = [i]
        used.add(i)
        changed = True
        while changed:
            changed = False
            for j, b in enumerate(items):
                if j in used:
                    continue
                if any(int(a2["hash"] - b["hash"]) <= threshold for a2 in (items[k] for k in members)):
                    members.append(j)
                    used.add(j)
                    changed = True
        if len(members) > 1:
            groups.append([items[k] for k in members])

    out = []
    for gi, members in enumerate(groups, start=1):
        rep = choose_representative(members)
        out.append(
            {
                "group_id": gi,
                "representative": rep,
                "members": [
                    {
                        "path": m["path"],
                        "phash": str(m["hash"]),
                        "file_size": m["size"],
                        "width": m["width"],
                        "height": m["height"],
                        "mtime_ns": m["mtime_ns"],
                        "max_distance_to_rep": int(rep["hash"] - m["hash"]),
                    }
                    for m in members
                ],
            }
        )
    return out


def choose_representative(members):
    """保留建议优先级（K11）：分辨率 → 文件大小 → mtime → 路径字典序。

    **只做建议，不执行删除。**
    """
    def key(m):
        w = m["width"] or 0
        h = m["height"] or 0
        return (-(w * h), -m["size"], -m["mtime_ns"], m["path"])

    return sorted(members, key=key)[0]


def build_suggestion_rows(groups):
    """把分组转成 CSV 行（keep / redundant 建议，不执行）。"""
    rows = []
    for g in groups:
        rep_path = g["representative"]["path"]
        for m in sorted(g["members"], key=lambda x: x["path"]):
            rows.append(
                (
                    g["group_id"],
                    "keep" if m["path"] == rep_path else "redundant",
                    m["path"],
                    m["phash"],
                    m["file_size"],
                    m["width"] if m["width"] is not None else "",
                    m["height"] if m["height"] is not None else "",
                    m["mtime_ns"],
                    m["max_distance_to_rep"],
                )
            )
    return rows


def write_keep_suggestions(groups, out_path):
    """写保留建议清单（唯一写盘动作；只写清单文件，不动用户文件）。"""
    rows = build_suggestion_rows(groups)
    return write_csv(out_path, SUGGESTION_HEADER, rows)
