"""主路径分词适配：libsimple（wangfenjin/simple）经 sqlite 扩展加载。

定位：**可选**主路径。libsimple 无 cp38/Windows 的 pip 轮子（阶段 0 实测），
用户需自备预编译 DLL（GitHub Release v0.7.1 提供 libsimple-windows-x64.zip 等）。

纪律：
  - 加载失败不冒充可用：抛 SimpleUnavailable，由 search/cli 显式报告"主路径未启用"；
  - char 兜底路径无条件可用，故"永远能查"不受影响。
"""

import os

_CACHE = {"loaded": False, "path": None}


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


def load_extension(conn):
    """把 libsimple 注册进 sqlite 连接（幂等）。不可用则抛 SimpleUnavailable。"""
    if _CACHE["loaded"]:
        return True
    lib = find_library()
    if lib is None:
        raise SimpleUnavailable(
            "未找到 libsimple 动态库：设置 PICRECALL_SIMPLE_LIB 或放置于项目根。"
            "（主路径未启用；检索将走 char 兜底路径）"
        )
    try:
        conn.enable_load_extension(True)
        conn.load_extension(lib)
    except Exception as exc:
        raise SimpleUnavailable("libsimple 加载失败（%s）" % exc)
    finally:
        try:
            conn.enable_load_extension(False)
        except Exception:
            pass
    _CACHE["loaded"] = True
    _CACHE["path"] = lib
    return True


def is_available(conn=None):
    try:
        if conn is not None:
            load_extension(conn)
        return _CACHE["loaded"]
    except SimpleUnavailable:
        return False


def simple_segment(text):
    """主路径分词：libsimple 词级切分。

    不可用时抛 SimpleUnavailable（不静默回落，由调用方决定降级策略）。
    """
    if not _CACHE["loaded"]:
        raise SimpleUnavailable("libsimple 未加载")
    raise SimpleUnavailable(
        "libsimple 已加载但尚未接线 simple_segment 实现（M1 实测后接线）"
    )
