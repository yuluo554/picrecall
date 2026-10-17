"""全部数值口径的唯一来源（K 纪律：数值只此一处，文档只引用不复述）。

任何模块都不得自行定义阈值/白名单/退出码字面量——一律 import 本模块。
"""

# ── 退出码语义（K9，冻结；锁进测试，README 与留档按"符合声明语义"判读）──
EXIT_OK = 0          # 成功（含"零命中""零重复组"这类合法空结果）
EXIT_FINDINGS = 1    # 运行完成但检出问题（业务判定，非崩溃）
EXIT_USAGE = 2       # 用法/输入错误
EXIT_MISSING_DEP = 3  # 依赖缺失契约（可选重件不可用）

# ── 模块 1：扫描白名单（K1）──
SUPPORTED_EXTS = ("png", "jpg", "jpeg", "bmp", "webp")

# ── 模块 2：OCR 口径（K4/K5）──
# 低于此置信度的行仍入库（保留原文）但计入 low_conf_lines；是否算"检出"由基准口径决定。
OCR_CONF_MIN = 0.50

# ── 模块 3：检索口径（K7）──
DEFAULT_SEARCH_LIMIT = 50

# ── 模块 4：相似图口径（K10/K11）──
# pHash 汉明距离阈值：<= 此距离视为同一组（默认只读，绝不删除）
PHASH_MAX_DISTANCE = 8
PHASH_HASH_SIZE = 16  # imagehash.phash(hash_size=16) → 256 bit

# ── 模块 5：基准口径（门槛随 manifest 下发，此处仅为兜底默认，K13）──
# 统一门槛（兜底）：manifest 未声明 `thresholds_by_profile` 时用这一套。
BENCH_DEFAULT_THRESHOLDS = {
    "ocr_line_recall": 0.90,
    "query_recall": 0.90,
}
# 分 profile 门槛（M4，D-22 定案）：char 与 simple 是**两种分词粒度**，对同一批
# 由"子串语义"派生的真值查询，其可达召回上限本就不同（词级要求查询对齐词边界）。
# 故按 profile 各设一套，**不并存两套默认**：有 `thresholds_by_profile` 即按 profile 取，
# 无则统一门槛。**未为达标而改已入仓真值**（D-18 红线）。
# 定标依据（M4 实测，见 plan/verify §M4 二）：两 profile 的 OCR 行识别率**完全相同**（0.9545），
# 差异**只在**检索侧；且 simple 的 5 处漏召回中 3 处根因是"真值查询取最长 CJK 片段前 4 字"
# 截断在词中间（词级无法命中跨词边界的子串），另 2 处（`failed`/`invalid`）是 OCR 切框，
# **两 profile 同源同受影响**。故 simple 的门槛按"词级语义"另定，不是把统一门槛下调凑数。
BENCH_THRESHOLDS_BY_PROFILE = {
    "char": {"ocr_line_recall": 0.90, "query_recall": 0.90},
    "simple": {"ocr_line_recall": 0.90, "query_recall": 0.80},
}
BENCH_SEED_DEFAULT = 20261016
BENCH_IMAGE_COUNT_DEFAULT = 60
# 近似重复族（M2）：独立子集，seed 与主集分开，避免互相牵动位级基准。
BENCH_DUPES_SEED_DEFAULT = 20261017
BENCH_DUPES_COUNT_DEFAULT = 6  # 族数；每族成员数见 bench.DUPES_MEMBERS（固定 3 张）

# ── 索引库默认位置（D-11）──
DB_FILENAME = ".picrecall.db"

# ── 分词 profile 标识（K6）──
PROFILE_CHAR = "char"      # 兜底路径：CJK 逐字切分 + unicode61（无条件可用）
PROFILE_SIMPLE = "simple"  # 主路径：libsimple 词级切分（需用户提供 DLL）


def supported_exts_set():
    """返回带点后缀集合，供扫描过滤（白名单只有这一份定义）。"""
    return {"." + e for e in SUPPORTED_EXTS}
