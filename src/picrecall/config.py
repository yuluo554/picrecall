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
BENCH_DEFAULT_THRESHOLDS = {
    "ocr_line_recall": 0.90,
    "query_recall": 0.90,
}
BENCH_SEED_DEFAULT = 20261016
BENCH_IMAGE_COUNT_DEFAULT = 60

# ── 索引库默认位置（D-11）──
DB_FILENAME = ".picrecall.db"

# ── 分词 profile 标识（K6）──
PROFILE_CHAR = "char"      # 兜底路径：CJK 逐字切分 + unicode61（无条件可用）
PROFILE_SIMPLE = "simple"  # 主路径：libsimple 词级切分（需用户提供 DLL）


def supported_exts_set():
    """返回带点后缀集合，供扫描过滤（白名单只有这一份定义）。"""
    return {"." + e for e in SUPPORTED_EXTS}
