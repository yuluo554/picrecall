"""K10 阈值一处定义守门（M2，HANDOFF-M2 §二 4）。

纪律：pHash 的**数值口径**（默认阈值、hash 位宽）只能有一处字面量——`config.py`。
其它模块一律 `import config` 取值；文档只引用不复述。

为何要这条门：口径散成两份时，改一处而另一处不跟，就会出现
"文档写 8、代码用 10"这类静默漂移，且**没有任何测试会红**。
本门用 AST（而非子串扫描）判定，避免被 `8  # 阈值` 这类注释误伤，
也避免被变量别名绕过。
"""

import ast
import os

from picrecall import config, dedupe

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src", "picrecall")

# K10 口径数值（来自 config，唯一真源）
PHASH_LITERALS = {
    config.PHASH_MAX_DISTANCE,   # 默认相似阈值
    config.PHASH_HASH_SIZE,      # pHash 位宽
}


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _literal_int_assignments(tree):
    """收集 `NAME = <int 字面量>` 形态的模块级赋值（含 AnnAssign）。"""
    found = {}
    for node in tree.body:  # 只看模块级
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if not isinstance(value, ast.Constant) or not isinstance(value.value, int) \
                or isinstance(value.value, bool):
            continue
        for t in targets:
            if isinstance(t, ast.Name):
                found[t.id] = value.value
    return found


def test_config_is_the_single_source_for_phash_numbers():
    """config 必须定义这两个口径常量（唯一真源）。"""
    assert isinstance(config.PHASH_MAX_DISTANCE, int)
    assert isinstance(config.PHASH_HASH_SIZE, int)
    assert config.PHASH_HASH_SIZE > 0
    assert 0 <= config.PHASH_MAX_DISTANCE <= config.PHASH_HASH_SIZE ** 2


def test_no_second_assignment_of_phash_numbers_in_package():
    """全包内**只有 config** 给这两个名字赋字面量（防第二份定义）。"""
    offenders = []
    for name in sorted(os.listdir(SRC_DIR)):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(_read(os.path.join(SRC_DIR, name)))
        assigns = _literal_int_assignments(tree)
        for var in ("PHASH_MAX_DISTANCE", "PHASH_HASH_SIZE"):
            if var in assigns and name != "config.py":
                offenders.append("%s: %s = %s" % (name, var, assigns[var]))
    assert offenders == [], "pHASH 口径在 config 之外被二次定义: %s" % offenders


def test_dedupe_does_not_hardcode_threshold_or_hash_size():
    """dedupe 只准引用 config；不得出现这两个口径的裸字面量赋值/默认参数。"""
    tree = ast.parse(_read(os.path.join(SRC_DIR, "dedupe.py")))

    # ① 不得有同名模块级赋值
    assigns = _literal_int_assignments(tree)
    assert "PHASH_MAX_DISTANCE" not in assigns
    assert "PHASH_HASH_SIZE" not in assigns

    # ② 函数默认参数不得把阈值/hash_size 写成**数字**字面量
    #    （`None` 是合法哨兵——表示"回落到 config"，不算第二处定义）
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.args.defaults:
            continue
        pairs = zip(node.args.args[-len(node.args.defaults):], node.args.defaults)
        for arg, default in pairs:
            if arg.arg in ("threshold", "hash_size"):
                is_number = isinstance(default, ast.Constant) \
                    and isinstance(default.value, int) \
                    and not isinstance(default.value, bool)
                assert not is_number, \
                    "dedupe.%s 的默认值被写死为数字字面量（应取 config）" % node.name

    # ③ 反向硬断言：源码里必须真的引用了 config 的取值
    src = _read(os.path.join(SRC_DIR, "dedupe.py"))
    assert "config.PHASH_MAX_DISTANCE" in src
    assert "config.PHASH_HASH_SIZE" in src


def test_dedupe_default_threshold_equals_config():
    """行为面：不传阈值时实际生效的就是 config 值（不是另一处巧合的数字）。"""
    import inspect

    sig = inspect.signature(dedupe.phash_groups)
    assert sig.parameters["threshold"].default is None, \
        "默认值应为 None 再回落到 config（否则两处口径）"
    src = inspect.getsource(dedupe.phash_groups)
    assert "config.PHASH_MAX_DISTANCE" in src
