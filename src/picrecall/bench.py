"""模块 5：真值基准（plan/05 §三/§四）。

两块：
  gen_synthetic  —— 确定性生成合成截图集 + manifest（植入真值）
  run_bench      —— 真值对账（识别率 + 检索命中率），观测运行时实算
  gen_dupes      —— 确定性生成**近似重复族**（模块 4 端到端"能真出组"的样例，M2）

纪律：
  - K13 确定性：自研 splitmix64 RNG（禁 stdlib random）、固定 seed、无时间戳、位级一致；
  - K14 真值只存"输入与期望"：manifest 禁 observed/recognized/hit_rate 一类字段；
  - 门槛随 manifest 下发（数据非代码），不硬编码在代码里；
  - 可证伪探活：--inject-defect 注入缺陷后基准必须打红。

口径（识别率 / 命中率）见 plan/05 §四；实现常量见本模块顶部 docstring 锚定。
"""

import os

from . import config
from .db import get_meta
from .serialize import write_json

MANIFEST_SCHEMA = "picrecall-bench/1"
DUPES_MANIFEST_SCHEMA = "picrecall-dupes/1"

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

# ── 近似重复族口径锚定（M2，plan/04 §六）──
# 为何是这样造"近似重复"（M2 实测，见 plan/verify §M2 一）：
#   ① pHash **不抗平移**：实测把底图平移 2px，汉明距离即达 26（>默认阈值 8）；
#      平移 12px 达 120。故"轻微位移"**不能**用作近似重复的构造手段（HANDOFF-M2 §二 1
#      的原提议据此被实测否决）。
#   ② 缩放可落在阈值内：0.70–1.30 各档实测族内最大距离 6（60 个底图逐一实测）。
#   ③ 亮度也能落阈值内，但"正/反向极端亮度"两成员之间会擦边（实测最大 8–10），
#      故本生成器**只用缩放**，不用亮度，且成员数压到 3。
#   ④ 低分辨率成员用 **BMP**（无压缩）编码 → 其字节数反而**大于**高分辨率成员，
#      使 K11 第①级（分辨率）与第②级（文件大小）判决**相反**——代表选择因此有区分度，
#      而不是"分辨率最高者恰好也是文件最大者"这种无信息量的巧合。
DUPES_MEMBER_SPECS = (
    {"role": "base", "scale": 1.00, "fmt": "PNG"},
    {"role": "hi_res", "scale": 1.15, "fmt": "PNG"},
    {"role": "lo_res_big", "scale": 0.95, "fmt": "BMP"},
)

# ── 规则驱动层口径锚定（M4，plan/05 §4.3）──
# 分工（两层不可混同）：
#   样本驱动层：读 manifest 的期望，对账"**声明过**的输入是否被正确处理"。
#   规则驱动层：**完全不读 manifest**，自造"构造上已知"的输入，从机制推导端点应有的表现
#               ——专治样本没覆盖的端点（空白/单字符/超长/坏图/空文件夹/无命中查询）。
# 为何期望不必来自真值文件：探针的输入是本层当场渲染/当场写盘的，故"输入是什么"由构造
#   本身给定，期望因此可由机制直接推出。这是 K14（真值只存输入与期望）的延伸：
#   规则层的输入与期望都由本层生成，**没有任何理由**去读 manifest——读了就退化成"第二个样本层"。
# 纪律：`run_rule_probes` 的签名与函数体**不得出现 manifest**；由测试证伪
#   （把 `_resolve_manifest` 打成抛异常 / 删掉 manifest → 本层结论必须逐项不变）。
RULE_PROBE_SINGLE_CHAR = "账"
RULE_PROBE_LONG_LINE = "配置项说明与错误提示信息"
RULE_PROBE_LONG_LINES = 24
RULE_PROBE_LINE_BOUND = 200
RULE_PROBE_IMPOSSIBLE_QUERY = "zzqqxxvv"
RULE_INJECT_DEFECTS = ("rule_blank_always_true", "rule_bound_ignored")


def _is_blank_observation(obs):
    """机制判定①：观测中**非空文本数为 0**（无文本像素 → 不应产生文本行）。

    入参是 `_observed()` 压出的 `(非空文本数, 总行数)`。
    """
    return obs[0] == 0


def _within_line_bound(n):
    """机制判定②：行数**有界且非零**（0 行属"无文本"场景，归判定①管）。"""
    return 0 < n <= RULE_PROBE_LINE_BOUND


def _rule_predicates(inject_defect=None):
    """取规则层判定函数；注入缺陷时返回**被破坏**的判定（可证伪探活用）。

    探活的机制：判定函数一旦被改成"恒真"，**对侧期望**必然失守——
    ① 空白判定恒真 → 单字符探针（要求"非空白"）红；
    ② 行数上界判定恒真 → 判定自身的边界自检（要求"越界为 False"）红。
    """
    if inject_defect == "rule_blank_always_true":
        return (lambda obs: True), _within_line_bound
    if inject_defect == "rule_bound_ignored":
        return _is_blank_observation, (lambda n: True)
    return _is_blank_observation, _within_line_bound


def _observed(observed_lines):
    """把 OCR 观测压成 `(非空文本数, 总行数)`（规则层判定函数的统一入参）。"""
    texts = [_normalize(o.get("text", "")) for o in observed_lines]
    return (sum(1 for t in texts if t), len(texts))


def _write_rule_probe_images(out_dir):
    """写出规则层**自造**的探针图（M4）。

    "输入是什么"由构造本身给定（本层当场渲染/写盘），故"期望是什么"可由机制直接推出——
    这正是本层**无需读 manifest** 的原因（K14 的延伸：真值只存输入与期望，而这里输入与
    期望都是本层自己造的）。返回 {标签: 相对文件名}；文件名固定，**不含绝对路径**
    （报告须双跑逐项一致，见 M4 DoD ④）。
    """
    from PIL import Image, ImageDraw

    names = {}
    # ① 全空白图：画布上无任何文本像素 → 不应产生文本行
    Image.new("RGB", (520, 160), (248, 248, 250)).save(
        os.path.join(out_dir, "probe_blank.png"), format="PNG")
    names["blank"] = "probe_blank.png"

    # ② 单字符图 → 应命中其字符（可检出 + 可检索）
    img = Image.new("RGB", (520, 160), (248, 248, 250))
    ImageDraw.Draw(img).text((20, 24), RULE_PROBE_SINGLE_CHAR,
                             font=_find_font(34), fill=(20, 20, 20))
    img.save(os.path.join(out_dir, "probe_single.png"), format="PNG")
    names["single"] = "probe_single.png"

    # ③ 超长文本图：同一长行重复多行 → 行数大但**有界**，且不得崩溃
    rng = _SplitMix64(0)
    img, _meta = _render("plain", [RULE_PROBE_LONG_LINE] * RULE_PROBE_LONG_LINES,
                         20, rng, Image, ImageDraw)
    img.save(os.path.join(out_dir, "probe_long.png"), format="PNG")
    names["long"] = "probe_long.png"

    # ④ 坏图：非图片字节 → 索引不得中断，检索不得崩溃
    with open(os.path.join(out_dir, "probe_corrupt.png"), "wb") as fh:
        fh.write(b"this is not an image")
    names["corrupt"] = "probe_corrupt.png"

    # ⑤ 空文件夹：无任何图片 → 索引不崩、检索返回空
    os.makedirs(os.path.join(out_dir, "empty"), exist_ok=True)
    names["empty_dir"] = "empty"
    return names


def run_rule_probes(conn, inject_defect=None):
    """规则驱动层（plan/05 §4.3）：**完全不读 manifest**，从机制推导端点应有的表现。

    与样本驱动层的分工：样本层读 manifest 的期望，对账"**声明过**的输入是否被正确处理"；
    本层自造构造上已知的输入，专治**样本没覆盖的端点**（全空白 / 单字符 / 超长 / 坏图 /
    空文件夹 / 无命中查询）。若本层也去读 manifest，就退化成"第二个样本层"，失去意义——
    故签名与函数体**不得出现 manifest**，并由 `tests/test_bench_rules.py` 三重证伪
    （① 源码不得含 manifest 字样；② 把 `_resolve_manifest` 打成抛异常仍给出同样结论；
      ③ 删掉 manifest 文件仍给出同样结论）。

    探针图在本层自建的**独立临时索引库**上跑，不污染调用方的库；只有"无命中查询"
    与"空白查询"两项直接读调用方的库（只读，验证检索侧机制）。

    `inject_defect` 注入**机制破坏**（可证伪探活）：判定函数被改成"恒真"后，
    对侧期望必然失守（如空白判定恒真 → 单字符探针红）。见 `_rule_predicates`。

    返回 {"available", "probes", "passed", "unavailable", "inject_defect"}；
    报告里的一切细节都用**固定标签与计数**，不含绝对路径（保证双跑逐项一致）。
    """
    import json
    import shutil
    import tempfile

    from . import db as _db, index as _index, ocr as _ocr, search as _search

    blank_ok, bound_ok = _rule_predicates(inject_defect)
    probes = []

    def add(name, kind, available, ok, detail):
        probes.append({"name": name, "kind": kind, "available": bool(available),
                       "ok": bool(ok), "detail": detail})

    tmp = tempfile.mkdtemp(prefix="picrecall-rule-")
    try:
        names = _write_rule_probe_images(tmp)

        # ── 探针库：本层自建的独立索引库（不污染调用方）──
        pconn = _db.connect(os.path.join(tmp, "probe.db"))
        try:
            _index.apply_scan(pconn, _index.scan_folder(tmp))
            path_to_id = {r["path"]: r["id"] for r in
                          pconn.execute("SELECT id, path FROM files")}

            def observed(fname):
                fid = _find_path_for(path_to_id, fname)
                if fid is None:
                    return []
                row = pconn.execute(
                    "SELECT line_json FROM ocr_text WHERE file_id = ?", (fid,)
                ).fetchone()
                return json.loads(row["line_json"]) if row is not None else []

            def status_of(fname):
                fid = _find_path_for(path_to_id, fname)
                if fid is None:
                    return None
                return pconn.execute(
                    "SELECT status FROM files WHERE id = ?", (fid,)
                ).fetchone()["status"]

            # 引擎不可用时**只**降级 OCR 依赖的探针，索引/检索侧探针照跑（如实标注）
            ocr_available = True
            ocr_reason = None
            try:
                _ocr.ocr_pending(pconn)  # 失败隔离（K5）保证坏图不中断整批
            except _ocr.MissingDependency as exc:
                ocr_available = False
                ocr_reason = str(exc)

            # ① 全空白图 → 非空文本数必须为 0
            if ocr_available:
                obs = _observed(observed(names["blank"]))
                add("blank_image_yields_no_text_line", "ocr", True, blank_ok(obs),
                    "非空文本行=%d（期望 0）" % obs[0])
            else:
                add("blank_image_yields_no_text_line", "ocr", False, False,
                    "OCR 引擎不可用（%s）" % ocr_reason)

            # ② 单字符图 → 必须检出其字符，且该字符可被检索到
            if ocr_available:
                obs = _observed(observed(names["single"]))
                has_text = not blank_ok(obs)
                fid = _find_path_for(path_to_id, names["single"])
                hits = _search.search(pconn, RULE_PROBE_SINGLE_CHAR)
                searchable = any(h["file_id"] == fid for h in hits)
                add("single_char_is_detected_and_searchable", "ocr",
                    True, has_text and searchable,
                    "非空文本行=%d，该字符检索命中=%s" % (obs[0], searchable))
            else:
                add("single_char_is_detected_and_searchable", "ocr", False, False,
                    "OCR 引擎不可用（%s）" % ocr_reason)

            # ③ 超长文本图 → 不崩溃（状态非 ocr_failed）且行数有界
            if ocr_available:
                n = len(observed(names["long"]))
                st = status_of(names["long"])
                add("long_text_does_not_crash_and_lines_bounded", "ocr", True,
                    (st != "ocr_failed") and bound_ok(n),
                    "状态=%s，观测行数=%d（期望 1..%d）" % (st, n, RULE_PROBE_LINE_BOUND))
            else:
                add("long_text_does_not_crash_and_lines_bounded", "ocr", False, False,
                    "OCR 引擎不可用（%s）" % ocr_reason)

            # ③' 上界判定自身的边界自检（给"上界被无视"的注入以牙齿）
            add("line_bound_predicate_rejects_overflow", "mechanism", True,
                bound_ok(RULE_PROBE_LINE_BOUND + 1) is False,
                "上界判定对 %d 行须为 False（越界拒绝）" % (RULE_PROBE_LINE_BOUND + 1))

            # ④ 坏图 → 索引不崩（台账行仍在、未被静默丢弃），检索不崩且无命中
            st = status_of(names["corrupt"])
            row_exists = st is not None
            hits = _search.search(pconn, RULE_PROBE_IMPOSSIBLE_QUERY)
            add("corrupt_image_survives_index_and_search_is_empty", "index", True,
                row_exists and st != "missing" and hits == [],
                "台账行存在=%s，状态=%s，无命中查询返回=%d"
                % (row_exists, st, len(hits)))
        finally:
            pconn.close()

        # ⑤ 空文件夹 → 索引不崩、库内 0 文件、检索返回空（独立库，避免牵动探针库的 missing 判定）
        econn = _db.connect(os.path.join(tmp, "empty.db"))
        try:
            scan = _index.scan_folder(os.path.join(tmp, names["empty_dir"]))
            _index.apply_scan(econn, scan)
            stats = _index.index_stats(econn)
            hits = _search.search(econn, RULE_PROBE_IMPOSSIBLE_QUERY)
        finally:
            econn.close()
        add("empty_folder_indexes_cleanly_and_search_is_empty", "index", True,
            len(scan) == 0 and stats["total_files"] == 0 and hits == [],
            "扫描到=%d，库内文件=%d，检索命中=%d"
            % (len(scan), stats["total_files"], len(hits)))

        # ⑥ 调用方库上的检索侧端点（只读）：无命中查询 / 无 token 查询都必须返回空、不崩
        absent = _search.search(conn, RULE_PROBE_IMPOSSIBLE_QUERY)
        blank_q = _search.search(conn, "   ")
        add("absent_and_tokenless_queries_return_empty", "search", True,
            absent == [] and blank_q == [],
            "无命中查询返回=%d，无 token 查询返回=%d" % (len(absent), len(blank_q)))

        return {
            "available": ocr_available,
            "probes": probes,
            "passed": all(p["ok"] for p in probes if p["available"]),
            "unavailable": [p["name"] for p in probes if not p["available"]],
            "inject_defect": inject_defect,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def default_data_dir():
    """默认数据目录（仓库内 `data/`）。

    按包路径推导，故**只在可编辑安装（源码树内）下成立**：非可编辑安装会把包复制到
    site-packages，推导结果落到 site-packages 之外而落空——调用方须给出显式 `--data`
    （见 `require_data_dir`）。这是 M0 登记的已知缺口，M5 实测确认并改为显式报错。
    """
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
    )


def require_data_dir(data_dir):
    """解析生效的数据目录：显式传入优先，否则用默认；默认目录不存在即报**可照做**的错。

    这条分支是为"非可编辑安装"准备的：默认目录落空时，与其让下游报一个指向
    site-packages 的莫名路径，不如在这里直接告诉用户该传什么。
    """
    resolved = data_dir or default_data_dir()
    if not os.path.isdir(resolved):
        raise FileNotFoundError(
            "数据目录不存在: %s（未显式传 --data 时按包路径推导；非可编辑安装会落空）"
            "——请显式指定仓库内的数据目录: --data <仓库>/data" % resolved
        )
    return resolved


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
    data_dir = require_data_dir(data_dir)
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
        # 分 profile 门槛（M4，D-22）：与统一门槛同处 manifest（数据非代码）；
        # run_bench 按索引库的 profile 取生效门槛，未声明即退回统一门槛。
        "thresholds_by_profile": {
            k: dict(v) for k, v in config.BENCH_THRESHOLDS_BY_PROFILE.items()
        },
        "images": images,
    }
    manifest_path = os.path.join(out_dir, "manifest.json")
    write_json(manifest_path, manifest)
    return manifest_path


def _scale_image(img, factor):
    """确定性缩放（LANCZOS）。用 round() 而非 int() 截断，避免累计偏一点。"""
    w, h = img.size
    nw = max(1, int(round(w * factor)))
    nh = max(1, int(round(h * factor)))
    if (nw, nh) == (w, h):
        return img.copy()
    # Pillow 10 起 Image.LANCZOS 仍在；9.x 需 Image.ANTIALIAS（已废弃于 10）。
    try:
        resample = img.Resampling.LANCZOS
    except AttributeError:  # Pillow < 9.1
        resample = getattr(img, "LANCZOS", getattr(img, "ANTIALIAS", 1))
    return img.resize((nw, nh), resample)


def gen_dupes(out_dir, data_dir=None, seed=None, count=None):
    """生成**近似重复族**合成集 + manifest（M2；模块 4 端到端真样例）。

    与 `gen_synthetic` 分开的独立子集：**不改动** `data/synthetic/manifest.json`
    （M1 已登记其 sha256/pixel_sha256，改动会让 M1 留档的基准数字失效）。

    每"族"含 3 张近似重复图（同一文本 + 同一版式，仅缩放/编码不同），
    族内 pHash 距离实测 ≤6（默认阈值 8），族间实测 ≥56 → 分组必出组且不误并。

    manifest 只存**输入与期望**（K14）：
      - `lines`/`queries`/`layout`：渲染了什么（与主集同口径）；
      - `family_id`：构造时即已知的"应同组"真值（是期望，不是观测）；
      - `role`/`scale`/`format`/`width`/`height`：该成员怎么造的。
    观测（实际分了几组、谁是代表）一律不入 manifest，由测试/调用方运行时实算。
    """
    from PIL import Image, ImageDraw

    seed = config.BENCH_DUPES_SEED_DEFAULT if seed is None else int(seed)
    count = config.BENCH_DUPES_COUNT_DEFAULT if count is None else int(count)
    data_dir = require_data_dir(data_dir)
    whitelist = _load_whitelist(data_dir)

    os.makedirs(out_dir, exist_ok=True)
    rng = _SplitMix64(seed)
    images = []

    for fam in range(1, count + 1):
        n_lines = min(rng.randint(2, 3), len(whitelist))
        pool = list(whitelist)
        chosen = [pool.pop(rng.next_u64() % len(pool)) for _ in range(n_lines)]
        kind = rng.choice(LAYOUT_KINDS)
        size = rng.choice(FONT_SIZES)

        # 同一族的底图只渲染一次，各成员由同一张底图派生（保证"近似"而非"相同"）
        base_img, layout_meta = _render(kind, chosen, size, rng, Image, ImageDraw)
        for spec in DUPES_MEMBER_SPECS:
            img = _scale_image(base_img, spec["scale"])
            name = "dup_%04d_%s.%s" % (fam, spec["role"], spec["fmt"].lower())
            path = os.path.join(out_dir, name)
            img.save(path, format=spec["fmt"])
            images.append(
                {
                    "file": name,
                    "family_id": fam,
                    "role": spec["role"],
                    "scale": spec["scale"],
                    "format": spec["fmt"],
                    "lines": list(chosen),
                    "queries": _derive_queries(chosen),
                    "layout": dict(layout_meta, width=img.size[0], height=img.size[1]),
                    "sha256": _sha256(path),
                    "pixel_sha256": _pixel_sha256(path),
                }
            )

    manifest = {
        "schema": DUPES_MANIFEST_SCHEMA,
        "seed": seed,
        "generator": "picrecall.bench.gen_dupes",
        "generator_version": _pkg_version(),
        "family_count": count,
        "members_per_family": len(DUPES_MEMBER_SPECS),
        "image_count": len(images),
        # 阈值随 manifest 下发（与主集同纪律：数据非代码）
        "thresholds": {"phash_max_distance": config.PHASH_MAX_DISTANCE},
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

    报告分两层（plan/05 §4.3）：
      - `ocr` / `search`：**样本驱动层**（读 manifest 对账）；
      - `rules`：**规则驱动层**（`run_rule_probes`，完全不读 manifest，专治样本外端点）。
    报告的细节一律用**相对文件名/固定标签**，不含绝对路径或时钟——保证同库双跑逐项一致
    （M4 DoD ④）。
    """
    import json

    from .search import search

    data_dir = require_data_dir(data_dir)
    manifest_path = _resolve_manifest(data_dir)
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    thr = dict(manifest.get("thresholds") or config.BENCH_DEFAULT_THRESHOLDS)
    # 分 profile 门槛（M4，D-22）：manifest 顶层键，与统一门槛同源下发（数据非代码）。
    # 未声明 → 不塞入，`_effective_thresholds` 即退回统一门槛（口径唯一，不并存两套默认）。
    by_profile = manifest.get("thresholds_by_profile")
    if by_profile:
        thr["thresholds_by_profile"] = {
            k: dict(v) for k, v in by_profile.items()
        }
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

    # 门槛标定（M4，D-22）：分 profile 门槛——char 与 simple 是**两种分词粒度**，
    # 同一门槛对二者不公平（真值查询派生方式与词级粒度错配，见 D-18）。
    # 未声明 `thresholds_by_profile` 时退回统一门槛（向后兼容，口径唯一）。
    prof = get_meta(conn, "tokenizer_profile", config.PROFILE_CHAR)
    eff = _effective_thresholds(thr, prof)
    sample_passed = (ocr_recall >= eff["ocr_line_recall"]) and \
                    (query_recall >= eff["query_recall"])

    # 规则驱动层（不读 manifest；见 run_rule_probes 的纪律声明）
    rules = run_rule_probes(conn, inject_defect=inject_defect)

    return {
        "thresholds": thr,
        "profile": prof,
        "effective_thresholds": eff,
        "ocr": {"total_lines": total_lines, "detected_lines": detected_lines,
                "recall": round(ocr_recall, 6),
                "recall_strict_single_line": round(ocr_recall_strict, 6),
                "strict_line_hits": strict_hits,
                "details": line_details},
        "search": {"total_queries": total_q, "recalled_queries": hit_q,
                   "recall": round(query_recall, 6), "false_positives": false_positives,
                   "details": query_details},
        "rules": rules,
        "passed": bool(sample_passed and rules["passed"]),
        "sample_passed": bool(sample_passed),
        "inject_defect": inject_defect,
    }


def _effective_thresholds(thr, profile):
    """按 profile 取生效门槛（M4，D-22）。

    `manifest.thresholds_by_profile[profile]` 若存在则**覆盖**统一门槛；
    未声明该键 → 退回统一门槛（口径唯一：要么统一，要么分 profile，不并存两套默认）。
    """
    out = dict(thr)
    by_profile = thr.get("thresholds_by_profile") or {}
    for key, value in (by_profile.get(profile) or {}).items():
        out[key] = value
    return {k: v for k, v in out.items() if not isinstance(v, dict)}


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
        "thresholds_by_profile": manifest.get("thresholds_by_profile"),
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
