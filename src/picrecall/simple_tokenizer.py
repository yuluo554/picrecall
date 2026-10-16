"""主路径分词适配：libsimple（wangfenjin/simple）经 sqlite 扩展加载。

定位：**可选**主路径。libsimple 无 cp38/Windows 的 pip 轮子（阶段 0 实测），
用户需自备预编译件（GitHub Release v0.7.1 提供 libsimple-windows-x64.zip 等）。

M1 实测接线要点（见 plan/verify/README.md §M1）：
  - libsimple 注册的是 **FTS5 tokenizer**（`tokenize='simple'`），并**不提供**任何
    逐串返回 token 的 SQL 函数；词级切分（cppjieba）只能经 `jieba_query()` 拿到，
    其输出形如 `"本月" AND "账单" AND "已" AND "生成"`，故本模块从引号词提取 token。
  - ⚠️ **进程级中止风险（实测）**：`jieba_query()` 在词典缺失时**不是抛异常，而是
    直接 FATAL 中止进程（exit 127）**。故本模块**先校验词典 5 件套**再调用，
    词典不全一律走 SimpleUnavailable 优雅降级，绝不把进程交给 cppjieba 去中止。
  - 所需词典 5 件（实测最小集，`pos_dict/` 不需要）：jieba.dict.utf8 / user.dict.utf8 /
    hmm_model.utf8 / idf.utf8 / stop_words.utf8。

纪律：
  - 加载失败不冒充可用：抛 SimpleUnavailable，由 search/cli 显式报告"主路径未启用"；
  - char 兜底路径无条件可用，故"永远能查"不受影响。
"""

import os
import re
import sqlite3

_CACHE = {"loaded": False, "path": None, "dict": None, "conn": None}

# 实测最小词典集（缺任一 → jieba_query 会进程级中止，故必须前置校验）
REQUIRED_DICT_FILES = (
    "jieba.dict.utf8",
    "user.dict.utf8",
    "hmm_model.utf8",
    "idf.utf8",
    "stop_words.utf8",
)

_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_CJK_CHAR = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_TOKEN_OR_GAP = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+|[A-Za-z0-9_]+")
_QUOTED = re.compile(r'"([^"]+)"')


class SimpleUnavailable(Exception):
    """libsimple 扩展不可用（不冒充可用）。"""


def find_library():
    """按 PICRECALL_SIMPLE_LIB 环境变量或常见文件名定位动态库。"""
    env = os.environ.get("PICRECALL_SIMPLE_LIB")
    if env and os.path.isfile(env):
        return env
    candidates = ["libsimple.dll", "simple.dll", "libsimple.so", "libsimple.dylib"]
    here = os.path.dirname(os.path.abspath(__file__))
    for root in (here, os.getcwd()):
        for name in candidates:
            p = os.path.join(root, name)
            if os.path.isfile(p):
                return p
    return None


def find_dict_dir(lib_path=None):
    """定位 cppjieba 词典目录：PICRECALL_SIMPLE_DICT 或动态库同级的 dict/。"""
    env = os.environ.get("PICRECALL_SIMPLE_DICT")
    if env and os.path.isdir(env):
        return env
    lib = lib_path or find_library()
    if lib:
        cand = os.path.join(os.path.dirname(os.path.abspath(lib)), "dict")
        if os.path.isdir(cand):
            return cand
    return None


def missing_dict_files(dict_dir=None):
    """返回缺失的必需词典文件列表（空列表 = 齐备）。"""
    d = dict_dir if dict_dir is not None else find_dict_dir()
    if not d:
        return list(REQUIRED_DICT_FILES)
    return [n for n in REQUIRED_DICT_FILES if not os.path.isfile(os.path.join(d, n))]


def availability():
    """探活三态：(可用?, 原因)。不加载、不中止进程——纯文件系统检查。"""
    lib = find_library()
    if lib is None:
        return False, "未找到 libsimple 动态库（设 PICRECALL_SIMPLE_LIB 或置于项目根）"
    d = find_dict_dir(lib)
    miss = missing_dict_files(d)
    if miss:
        return False, "cppjieba 词典不全（缺 %s；目录 %s）" % (", ".join(miss), d or "未定位到")
    return True, "libsimple 动态库与词典齐备"


def _new_conn(lib):
    """建一条专用内存连接并加载扩展 + 绑定词典（jieba_query 前置条件）。"""
    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(True)
    try:
        conn.load_extension(lib)
    finally:
        try:
            conn.enable_load_extension(False)
        except Exception:
            pass
    # 必须先绑定词典再调用 jieba_query（否则进程级中止，实测 exit 127）
    conn.execute("SELECT jieba_dict(?)", (find_dict_dir(lib),))
    return conn


def load_extension(conn):
    """加载 libsimple（幂等）。不可用则抛 SimpleUnavailable，不冒充可用。

    注意：本函数只做"能加载且词典齐备"的判定；真正需要 jieba_query 的分词走
    模块内专用连接（见 simple_segment），不依赖传入的 conn。
    """
    if _CACHE["loaded"]:
        return True
    ok, reason = availability()
    if not ok:
        raise SimpleUnavailable("%s（主路径未启用；检索将走 char 兜底路径）" % reason)
    lib = find_library()
    try:
        _CACHE["conn"] = _new_conn(lib)
    except SimpleUnavailable:
        raise
    except Exception as exc:
        raise SimpleUnavailable("libsimple 加载失败（%s）" % exc)
    _CACHE["loaded"] = True
    _CACHE["path"] = lib
    _CACHE["dict"] = find_dict_dir(lib)
    return True


def is_available(conn=None):
    ok, _reason = availability()
    return bool(ok)


def simple_segment(text):
    """主路径分词：libsimple 词级切分（CJK 走 cppjieba，ASCII 词保持整体）。

    输出与 `char` 路径同构（空格连接的 token 串），故 FTS5 表无需改动。
    token 顺序**保持原文顺序**（CJK 词级 + ASCII 整词交错），否则 phrase 匹配会失真。
    不可用时抛 SimpleUnavailable（不静默回落，由调用方决定降级策略）。
    """
    if not _CACHE["loaded"]:
        load_extension(None)
    conn = _CACHE["conn"]
    out = []
    for m in _TOKEN_OR_GAP.finditer(text):
        run = m.group(0)
        if _CJK_CHAR.match(run[0]):
            query = conn.execute("SELECT jieba_query(?)", (run,)).fetchone()[0]
            out.extend(_QUOTED.findall(query))
        else:
            out.append(run)
    return " ".join(out)


def simple_tokens(text):
    """同 simple_segment，但返回 token 列表（供测试与对账直接消费）。"""
    return simple_segment(text).split()


def _reset_cache():
    """测试用：清空加载缓存（避免跨用例串味）。"""
    _CACHE.update({"loaded": False, "path": None, "dict": None, "conn": None})
