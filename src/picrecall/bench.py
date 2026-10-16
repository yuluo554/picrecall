"""模块 5：真值基准（plan/05 §三/§四）。

两块：
  gen_synthetic  —— 确定性生成合成截图集 + manifest（植入真值）
  run_bench      —— 真值对账（识别率 + 检索命中率），观测运行时实算

纪律：
  - K13 确定性：自研 splitmix64 RNG（禁 stdlib random）、固定 seed、无时间戳、位级一致；
  - K14 真值只存"输入与期望"：manifest 禁 observed/recognized/hit_rate 一类字段；
  - 门槛随 manifest 下发（数据非代码），不硬编码在代码里；
  - 可证伪探活：--inject-defect 注入缺陷后基准必须打红。

口径（识别率 / 命中率）见 plan/05 §四；实现常量见本模块顶部 docstring 锚定。
"""

import os

from . import config
from .serialize import write_json

MANIFEST_SCHEMA = "picrecall-bench/1"

# ── 口径锚定（plan/05 §四，唯一实现处，文档只引用）──
# OCR 识别率口径：以"合成图上应识别出的文本行是否被检出"计。
#   "被检出" = 该行归一化字符序列 **包含于** OCR 输出行之一（归一化后），
#             且该输出行置信度 >= config.OCR_CONF_MIN。
#   已知取舍：以"包含"而非"逐字相等"，因 OCR 对中文标点/空格常有不稳定差异，
#             该取舍使识别率口径偏宽松（README 与报告显式声明）。
# 检索命中率口径：query 的返回图片集合 **包含** manifest 中声明该 query 的图片集合（召回优先）；
#   同时另记精确率（返回集中非真值图片数），如实报告不掩盖误召回。


def _default_data_dir():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
    )


def _resolve_manifest(data_dir):
    """定位 manifest：`--data` 既可指仓库 data/（→ data/synthetic/manifest.json），
    也可直接指生成输出目录（→ <dir>/manifest.json）。"""
    direct = os.path.join(data_dir, "manifest.json")
    if os.path.isfile(direct):
        return direct
    nested = os.path.join(data_dir, "synthetic", "manifest.json")
    if os.path.isfile(nested):
        return nested
    raise FileNotFoundError(
        "找不到 manifest（已找 %s 与 %s）；请先运行: picrecall bench gen --data <dir>"
        % (direct, nested)
    )


class _SplitMix64:
    """自研确定性 RNG（stdlib random 不承诺跨版本序列一致）。"""

    def __init__(self, seed):
        self.state = (seed ^ 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def randint(self, lo, hi):
        """闭区间 [lo, hi]。"""
        span = hi - lo + 1
        return lo + (self.next_u64() % span)

    def choice(self, seq):
        return seq[self.next_u64() % len(seq)]


LAYOUT_KINDS = ("plain", "titlebar", "bubble_left", "bubble_right", "list")
FONT_SIZES = (20, 24, 28, 34)


def _load_whitelist(data_dir):
    path = os.path.join(data_dir, "whitelist_texts.txt")
    if not os.path.isfile(path):
        raise FileNotFoundError("白名单文本集缺失: %s" % path)
    lines = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            s = raw.strip()
            if s and not s.startswith("#"):
                lines.append(s)
    if not lines:
        raise ValueError("白名单文本集为空: %s" % path)
    return lines


def _find_font(size):
    from PIL import ImageFont

    for name in ("msyh.ttc", "msyh.ttf", "arial.ttf", "DejaVuSans.ttf"):
        for base in (r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
    return ImageFont.load_default()


def gen_synthetic(out_dir, data_dir=None, seed=None, count=None, quiet=False):
    """生成合成截图集 + manifest。返回 manifest 路径。

    确定性：同一 seed + 同一白名单 → 图片字节与 manifest 逐字节一致。
    """
    from PIL import Image, ImageDraw

    seed = config.BENCH_SEED_DEFAULT if seed is None else int(seed)
    count = config.BENCH_IMAGE_COUNT_DEFAULT if count is None else int(count)
    data_dir = data_dir or _default_data_dir()
    whitelist = _load_whitelist(data_dir)

    os.makedirs(out_dir, exist_ok=True)
    rng = _SplitMix64(seed)
    images = []

    for idx in range(1, count + 1):
        n_lines = rng.randint(1, 3)
        # 抽样**不重复**（重复行只会重复计真值分母，不增加覆盖价值）
        n_lines = min(n_lines, len(whitelist))
        pool = list(whitelist)
        chosen = []
        for _ in range(n_lines):
            chosen.append(pool.pop(rng.next_u64() % len(pool)))
        kind = rng.choice(LAYOUT_KINDS)
        size = rng.choice(FONT_SIZES)

        img, layout_meta = _render(kind, chosen, size, rng, Image, ImageDraw)
        name = "img_%04d.png" % idx
        path = os.path.join(out_dir, name)
        img.save(path, format="PNG", optimize=False)

        images.append(
            {
                "file": name,
                "lines": chosen,
                "queries": _derive_queries(chosen),
                "layout": layout_meta,
                "sha256": _sha256(path),
            }
        )

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "seed": seed,
        "generator": "picrecall.bench",
        "generator_version": _pkg_version(),
        "image_count": count,
        "thresholds": dict(config.BENCH_DEFAULT_THRESHOLDS),
        "images": images,
    }
    manifest_path = os.path.join(out_dir, "manifest.json")
    write_json(manifest_path, manifest)
    return manifest_path


def _text_width(draw, text, font):
    """测量文本渲染宽度（Pillow 版本差异下走双通道）。"""
    try:
        return int(draw.textlength(text, font=font))
    except AttributeError:
        w, _ = draw.textsize(text, font=font)  # 老 Pillow
        return int(w)


def _render(kind, lines, size, rng, Image, ImageDraw):
    """按版式渲染（确定性：噪声也走 rng）。

    画布尺寸**按实测文本宽度**决定——否则长文本在固定宽度下被裁掉，
    manifest 却仍声明"这行渲染过"，真值就成了假的（实测 img_0005 即栽在此）。
    """
    pad = 24
    gutter = 160 if kind in ("bubble_left", "bubble_right") else 0
    font = _find_font(size)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    text_w = max(_text_width(probe, line, font) for line in lines)
    width = max(520, text_w + 2 * pad + gutter)
    height = 60 + (size + 14) * len(lines) + (20 if kind == "titlebar" else 0)

    bg = (248, 248, 250) if kind != "titlebar" else (255, 255, 255)
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    y = 24
    if kind == "titlebar":
        draw.rectangle([0, 0, width, 30], fill=(230, 234, 240))
        draw.text((12, 6), "Screenshot", font=_find_font(16), fill=(60, 60, 60))
        y = 46
    for line in lines:
        if kind == "bubble_left":
            draw.rounded_rectangle([16, y - 6, 16 + text_w + 2 * pad, y + size + 6], radius=10,
                                   fill=(255, 255, 255), outline=(210, 214, 220))
            draw.text((28, y), line, font=font, fill=(20, 20, 20))
        elif kind == "bubble_right":
            x0 = width - 16 - (text_w + 2 * pad)
            draw.rounded_rectangle([x0, y - 6, width - 16, y + size + 6], radius=10,
                                   fill=(220, 240, 220), outline=(200, 220, 200))
            draw.text((x0 + 12, y), line, font=font, fill=(20, 20, 20))
        elif kind == "list":
            draw.ellipse([20, y + size // 2 - 3, 26, y + size // 2 + 3], fill=(120, 130, 140))
            draw.text((36, y), line, font=font, fill=(20, 20, 20))
        else:
            draw.text((20, y), line, font=font, fill=(20, 20, 20))
        y += size + 14

    return img, {"kind": kind, "font_size": size, "line_count": len(lines),
                 "width": width, "height": height}


def _derive_queries(lines):
    """从渲染文本派生"应命中查询词"（真值）：取每行的 CJK 片段或首个英文词。"""
    import re

    queries = []
    for line in lines:
        cjk = re.findall(r"[\u4e00-\u9fff]{2,}", line)
        if cjk:
            queries.append(max(cjk, key=len)[:4])
        words = re.findall(r"[A-Za-z]{3,}", line)
        if words:
            queries.append(words[0])
    # 去重且保持确定性顺序
    seen = set()
    out = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def _sha256(path):
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _pkg_version():
    from . import __version__

    return __version__


def _normalize(s):
    """归一化：去所有空白（OCR 对空格常不稳定，见口径取舍声明）。"""
    return "".join(s.split())


def run_bench(conn, data_dir=None, inject_defect=None, thresholds=None, quiet=False):
    """真值对账：识别率（逐行）+ 检索命中率（逐 query），观测运行时实算。

    manifest 只提供期望（lines/queries/thresholds），观测由本函数实算（K14）。
    """
    import json

    from .search import search

    data_dir = data_dir or _default_data_dir()
    manifest_path = _resolve_manifest(data_dir)
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    thr = dict(manifest.get("thresholds") or config.BENCH_DEFAULT_THRESHOLDS)
    if thresholds:
        thr.update(thresholds)

    # 逐图：从索引库读实算观测
    path_to_id = {
        row["path"]: row["id"]
        for row in conn.execute("SELECT id, path FROM files")
    }
    images = manifest["images"]

    total_lines = detected_lines = 0
    line_details = []
    for item in images:
        fname = item["file"]
        target = _find_path_for(path_to_id, fname)
        observed_lines = []
        if target is not None:
            row = conn.execute(
                "SELECT line_json FROM ocr_text WHERE file_id = ?", (target,)
            ).fetchone()
            if row is not None:
                observed_lines = json.loads(row["line_json"])
        if inject_defect == "ocr_drop":
            observed_lines = observed_lines[: max(0, len(observed_lines) // 2)]

        for expected in item["lines"]:
            total_lines += 1
            ne = _normalize(expected)
            hit = any(
                _normalize(o["text"]) and ne in _normalize(o["text"])
                and float(o["conf"]) >= config.OCR_CONF_MIN
                for o in observed_lines
            )
            if hit:
                detected_lines += 1
            line_details.append({"file": fname, "expected": expected, "detected": hit})

    ocr_recall = (detected_lines / total_lines) if total_lines else 0.0

    # 逐 query：检索召回
    query_details = []
    queries = []
    for item in images:
        for q in item["queries"]:
            if q not in queries:
                queries.append(q)
    total_q = hit_q = 0
    false_positives = 0
    for q in queries:
        truth = {i["file"] for i in images if q in i["queries"]}
        hits = search(conn, q, limit=1000)
        got = {os.path.basename(h["path"]) for h in hits}
        if inject_defect == "search_drop":
            got = set(sorted(got)[: max(0, len(got) // 2)])
        total_q += 1
        ok = truth.issubset(got)
        if ok:
            hit_q += 1
        false_positives += len(got - truth)
        query_details.append({"query": q, "expected_files": sorted(truth),
                              "got_files": sorted(got), "recalled": ok})

    query_recall = (hit_q / total_q) if total_q else 0.0
    passed = (ocr_recall >= thr["ocr_line_recall"]) and (query_recall >= thr["query_recall"])

    return {
        "thresholds": thr,
        "ocr": {"total_lines": total_lines, "detected_lines": detected_lines,
                "recall": round(ocr_recall, 6), "details": line_details},
        "search": {"total_queries": total_q, "recalled_queries": hit_q,
                   "recall": round(query_recall, 6), "false_positives": false_positives,
                   "details": query_details},
        "passed": passed,
        "inject_defect": inject_defect,
    }


def _find_path_for(path_to_id, fname):
    for p, fid in path_to_id.items():
        if os.path.basename(p) == fname:
            return fid
    return None


def check_generated(out_dir, data_dir=None, seed=None, count=None):
    """`gen --check`：重新生成到临时目录，与既有 manifest 逐字节比对。

    图片本体按 manifest 登记的 sha256 比对（图片不入 git，位级一致以 sha256 为锚）。
    """
    import json
    import shutil
    import tempfile

    existing = os.path.join(out_dir, "manifest.json")
    if not os.path.isfile(existing):
        return {"ok": False, "reason": "manifest 不存在: %s" % existing}
    with open(existing, "r", encoding="utf-8") as fh:
        old = json.load(fh)

    # 未显式给定 seed/count 时，从既有 manifest 派生——
    # 否则用户少带一个参数就会得到"假漂移"（实测：--count 不一致即误报）。
    if seed is None:
        seed = old.get("seed")
    if count is None:
        count = old.get("image_count")

    tmp = tempfile.mkdtemp(prefix="picrecall-check-")
    try:
        new_manifest = gen_synthetic(tmp, data_dir=data_dir, seed=seed, count=count, quiet=True)
        with open(new_manifest, "r", encoding="utf-8") as fh:
            new = json.load(fh)
        if new != old:
            return {"ok": False, "reason": "manifest 不一致（重生成漂移）"}
        # 图片 sha256 逐一比对
        for item in old["images"]:
            p = os.path.join(out_dir, item["file"])
            if not os.path.isfile(p):
                return {"ok": False, "reason": "图片缺失: %s" % item["file"]}
            if _sha256(p) != item["sha256"]:
                return {"ok": False, "reason": "图片字节漂移: %s" % item["file"]}
        return {"ok": True, "images": len(old["images"])}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
