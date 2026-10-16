"""冻结态自检（交付面）：依赖探活 + 数据目录 + 口径常量一致性。

探活打在**消费处**：真调用关键 API（FTS5 查询、PIL 打开），不是只看"函数存在"。
依赖缺失走 exit 3 契约（不抛裸异常）。
"""

import os
import sys

from . import SCHEMA_VERSION, __version__, config


def _probe(name, fn):
    try:
        detail = fn()
        return {"name": name, "ok": True, "detail": detail}
    except Exception as exc:
        return {"name": name, "ok": False, "detail": "%s: %s" % (type(exc).__name__, exc)}


def _probe_sqlite_fts5():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(a, tokenize='unicode61')")
    conn.execute("INSERT INTO t VALUES ('账单 已 生成')")
    n = conn.execute("SELECT count(*) FROM t WHERE t MATCH ?", ('"账单"',)).fetchone()[0]
    conn.close()
    if n != 1:
        raise AssertionError("FTS5 短中文查询探活失败（命中 %d，应为 1）" % n)
    return "FTS5 + unicode61 短中文查询可用"


def _probe_pillow():
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (80, 40), "white")
    ImageDraw.Draw(img).text((5, 5), "ok", font=ImageFont.load_default(), fill="black")
    return "Pillow 渲染可用"


def _probe_ocr():
    from .ocr import load_engine

    engine = load_engine()
    return "OCR 引擎已加载: %s" % type(engine).__name__


def _probe_imagehash():
    import imagehash  # noqa: F401

    return "imagehash 可用"


def _check_config():
    problems = []
    if not (0.0 < config.OCR_CONF_MIN <= 1.0):
        problems.append("OCR_CONF_MIN 越界")
    if not (0 <= config.PHASH_MAX_DISTANCE <= config.PHASH_HASH_SIZE ** 2):
        problems.append("PHASH_MAX_DISTANCE 越界")
    codes = {config.EXIT_OK, config.EXIT_FINDINGS, config.EXIT_USAGE, config.EXIT_MISSING_DEP}
    if codes != {0, 1, 2, 3}:
        problems.append("退出码常量不齐备")
    if config.PROFILE_CHAR not in (config.PROFILE_CHAR, config.PROFILE_SIMPLE):
        problems.append("profile 常量异常")
    return problems


def run_selftest(require_ocr=False):
    """执行自检，返回结果字典（含缺依赖时的 ok=False 与 exit 码建议）。"""
    checks = [
        _probe("sqlite-fts5", _probe_sqlite_fts5),
        _probe("pillow", _probe_pillow),
        _probe("imagehash", _probe_imagehash),
    ]
    ocr_probe = _probe("ocr", _probe_ocr)
    checks.append(ocr_probe)

    config_problems = _check_config()

    # OCR 缺席：默认只警告（核心三命令的 index/search/dedupe 不需要 OCR 引擎即可运行），
    # require_ocr 时才升级为硬失败（exit 3 契约）。
    hard_fail = [c for c in checks if not c["ok"] and c["name"] != "ocr"]
    ocr_missing = not ocr_probe["ok"]
    exit_code = config.EXIT_OK
    if hard_fail or config_problems or (require_ocr and ocr_missing):
        exit_code = config.EXIT_MISSING_DEP

    return {
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
        "python": sys.version.split()[0],
        "checks": checks,
        "config_problems": config_problems,
        "ocr_available": not ocr_missing,
        "exit_code": exit_code,
    }


def data_dir_default():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
    )
