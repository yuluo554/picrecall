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
#   "被检出" = 该行归一化字符序列 **包含于** OCR 输出行的**连续若干条拼接串**（归一化后），
#             且参与拼接的输出行置信度均 >= config.OCR_CONF_MIN。
#   为何是"连续若干条"而非"单条"（M1 实测修正）：OCR 会把**同一条渲染行**切成多个检测框
#             （实测 img_0010：`config error: timeout 3000` → `config` + `error:timeout3000`），
#             若只认"含于单条"，正确识别会被误判为未检出（60 图集实测 0.8909 → 0.9545）。
#   已知取舍：以"包含"而非"逐字相等"，因 OCR 对中文标点/空格常有不稳定差异；
#             该取舍使识别率口径偏宽松，故**同时另记严格单条命中数**（strict_line_hits）
#             供交叉核验，README 与报告显式声明。
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
                "pixel_sha256": _pixel_sha256(path),
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


def _pixel_sha256(path):
    """可移植内容指纹：对**解码后的原始像素字节**取 sha256。

    为什么要它（M1 实测发现）：PNG 文件字节依赖编码器版本——同一张图在
    Pillow 10.4.0 与 12.3.0 下 IDAT 压缩流不同（实测像素 0 差异、文件 sha256 不同）。
    故文件 sha256 只在"生成它的那套环境"里可比；`pixel_sha256` 跨环境稳定，
    用于把"内容真值"钉住，并在文件字节不一致时区分"编码器差异"与"内容真的漂移"。
    """
    from PIL import Image

    with Image.open(path) as im:
        raw = im.convert("RGB").tobytes()
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def _pkg_version():
    from . import __version__

    return __version__


def _normalize(s):
    """归一化：去所有空白（OCR 对空格常不稳定，见口径取舍声明）。"""
    return "".join(s.split())


def _contained_in_contiguous_run(needle, texts):
    """needle 是否含于 texts 中**连续若干条**的拼接串（O(n^2)，n 很小）。

    OCR 会把同一条渲染行切成多个相邻检测框，故判定须允许跨相邻框拼接；
    但只允许**连续**拼接（不是任意子集），以免把图上相距很远的词误拼成假命中。
    """
    if not needle:
        return False
    n = len(texts)
    for i in range(n):
        acc = ""
        for j in range(i, n):
            acc += texts[j]
            if needle in acc:
                return True
            if len(acc) > len(needle) * 4 + 64:
                break  # 拼接已远超目标长度，再拼无意义（保性能）
    return False


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
    strict_hits = 0
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

        # 只保留达阈值的输出行参与判定（置信度是口径的一部分）
        good = [o for o in observed_lines if float(o["conf"]) >= config.OCR_CONF_MIN]
        texts = [_normalize(o["text"]) for o in good]
        texts = [t for t in texts if t]

        for expected in item["lines"]:
            total_lines += 1
            ne = _normalize(expected)
            # 严格口径：含于**单条**输出行
            strict = any(ne in t for t in texts)
            # 主口径：含于**连续若干条**输出行的拼接串（OCR 会把一条渲染行切成多个框）
            hit = strict or _contained_in_contiguous_run(ne, texts)
            if strict:
                strict_hits += 1
            if hit:
                detected_lines += 1
            line_details.append({"file": fname, "expected": expected, "detected": hit,
                                 "strict": strict})

    ocr_recall = (detected_lines / total_lines) if total_lines else 0.0
    ocr_recall_strict = (strict_hits / total_lines) if total_lines else 0.0

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
                "recall": round(ocr_recall, 6),
                "recall_strict_single_line": round(ocr_recall_strict, 6),
                "strict_line_hits": strict_hits,
                "details": line_details},
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
    """`gen --check`：重新生成到临时目录，与既有 manifest 比对。

    两层判据（M1 实测校准，见 plan/verify §M1）：

    ① **完整性（严格，篡改必红）**：磁盘上的每张图，其文件 sha256 必须与 manifest
       登记值一致。任何字节改动（含在 IEND 之后追加字节）→ 红。
       注意：不能用"解码像素一致"来放过字节不一致——尾部追加字节**不改像素**，
       若用像素判据放行，篡改就会被误判成"编码器差异"，守门即失效。

    ② **可复现性（信息性，不改变 ① 的判定）**：本环境重新生成的 manifest 与既有
       manifest 是否逐字节一致。实测：PNG 的 IDAT 压缩流依赖 Pillow 版本
       （10.4.0 vs 12.3.0：同一张图像素 0 差异、文件字节不同），故跨环境可能报
       "编码器字节差异"——这是**环境差异**，不是数据漂移，如实标注并给出
       `pixel_sha256`（跨环境稳定的像素指纹）供交叉核验。
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

    # ① 完整性：磁盘文件 vs manifest 登记（篡改必红）
    for item in old["images"]:
        p = os.path.join(out_dir, item["file"])
        if not os.path.isfile(p):
            return {"ok": False, "reason": "图片缺失: %s" % item["file"]}
        if _sha256(p) != item["sha256"]:
            want_px = item.get("pixel_sha256")
            if want_px and _pixel_sha256(p) == want_px:
                # 内容未变但字节变了：只可能是"换了编码器重写"，仍如实报红（不放过篡改）
                return {"ok": False,
                        "reason": "图片字节与登记值不一致（内容一致，疑似编码器差异）: %s"
                                  % item["file"]}
            return {"ok": False, "reason": "图片字节漂移: %s" % item["file"]}

    tmp = tempfile.mkdtemp(prefix="picrecall-check-")
    try:
        new_manifest = gen_synthetic(tmp, data_dir=data_dir, seed=seed, count=count, quiet=True)
        with open(new_manifest, "r", encoding="utf-8") as fh:
            new = json.load(fh)

        # ②a 真值面（输入与期望）必须一致——真漂移在这里先现形
        old_truth = _truth_view(old)
        new_truth = _truth_view(new)
        if old_truth != new_truth:
            return {"ok": False, "reason": "manifest 真值不一致（重生成漂移）",
                    "diff": _first_diff(old_truth, new_truth)}

        # ②b 内容面：像素指纹（跨环境稳定）必须一致——内容真的变了就红
        for o_item, n_item in zip(old["images"], new["images"]):
            want = o_item.get("pixel_sha256")
            if want is None:
                continue
            if n_item.get("pixel_sha256") != want:
                return {"ok": False,
                        "reason": "图片内容漂移（像素指纹不一致）: %s" % o_item["file"]}

        # ②c 字节面：本环境能否逐字节复现既有 manifest（环境差异信息，不改变 ① 判定）
        encoder_mismatch = [
            o["file"] for o, n in zip(old["images"], new["images"])
            if o.get("sha256") != n.get("sha256")
        ]
        if encoder_mismatch:
            return {"ok": True, "images": len(old["images"]),
                    "note": "本环境编码器字节差异 %d 张（像素指纹一致，非漂移）"
                            % len(encoder_mismatch),
                    "encoder_mismatch": sorted(encoder_mismatch)}
        return {"ok": True, "images": len(old["images"])}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _truth_view(manifest):
    """真值视图：剔除环境相关的字节指纹，只留输入与期望（用于漂移判定）。"""
    return {
        "schema": manifest.get("schema"),
        "seed": manifest.get("seed"),
        "generator": manifest.get("generator"),
        "generator_version": manifest.get("generator_version"),
        "image_count": manifest.get("image_count"),
        "thresholds": manifest.get("thresholds"),
        "images": [
            {"file": i["file"], "lines": i["lines"], "queries": i["queries"], "layout": i["layout"]}
            for i in manifest.get("images", [])
        ],
    }


def _first_diff(a, b):
    """给出第一处真值差异的可读定位（便于排障，不改变判定）。"""
    if a.get("image_count") != b.get("image_count"):
        return "image_count: %s vs %s" % (a.get("image_count"), b.get("image_count"))
    if a.get("seed") != b.get("seed"):
        return "seed: %s vs %s" % (a.get("seed"), b.get("seed"))
    for x, y in zip(a.get("images", []), b.get("images", [])):
        if x != y:
            return "图片 %s 真值不同" % x.get("file")
    return "未定位到具体差异"
