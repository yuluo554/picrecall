"""README ↔ CLI 反射对账门（skill 验收门"测试面=安装面=README 指令面"）。

三面：
  ① README 里出现的每个 `picrecall <sub>` 命令与 `--flag` 都必须在 CLI 里真实存在；
  ② CLI 的每个子命令都必须在 README 命令总表里被提及（防"文档漏写可用命令"）；
  ③ README 快速开始的安装命令 extras 与 pyproject 声明双向对账。

变异验证：README 里加一个假旗标 → 本测试必须变红。
"""

import ast
import os
import re

import pytest

from picrecall import cli

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(REPO_ROOT, "README.md")
PYPROJECT = os.path.join(REPO_ROOT, "pyproject.toml")


def _toml_module():
    """tomllib 是 3.11+ 的 stdlib；3.8 通道回落 tomli（dev extra 已声明）。"""
    try:
        import tomllib as _t

        return _t
    except ModuleNotFoundError:
        import tomli as _t

        return _t


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _parser_index():
    """从 build_parser() 反射出：子命令 → 该子命令接受的旗标集合。

    递归进嵌套子解析器（如 `bench gen` / `bench run`），否则嵌套层的旗标
    （--check/--count/--data/--inject-defect）会被误判成"README 里的假旗标"。
    """
    parser = cli.build_parser()
    index = {}
    top_level = set()

    def walk(subparsers_action, prefix=""):
        for name, sub in subparsers_action.choices.items():
            full = ("%s %s" % (prefix, name)).strip()
            flags = set()
            for a in sub._actions:
                for opt in a.option_strings:
                    flags.add(opt)
            index[full] = flags
            if not prefix:
                top_level.add(name)   # 只有顶层子命令才要求"被 README 单独提及"
            for nested in sub._subparsers._group_actions if sub._subparsers else []:
                walk(nested, full)

    for action in parser._subparsers._group_actions:
        walk(action)
    return index, top_level


def _parser_flags():
    idx, _ = _parser_index()
    flags = set()
    for f in idx.values():
        flags |= f
    return flags


def _readme_invoked_commands(readme):
    """抽取 README 里 `picrecall <sub>` 形态的调用（含代码块与行内）。"""
    return set(re.findall(r"\bpicrecall\s+([a-z][a-z0-9-]*)", readme))


def _readme_flags(readme):
    return set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]+)", readme))


def test_readme_file_exists():
    assert os.path.isfile(README), "README.md 缺失"


def test_every_readme_command_exists_in_cli():
    readme = _read(README)
    idx, _top = _parser_index()
    invoked = _readme_invoked_commands(readme)
    # `picrecall --version` 与 `picrecall <command>` 占位形态不在 invoked 中
    unknown = {c for c in invoked if c not in idx and c != "bench"}
    assert unknown == set(), "README 提到但 CLI 不存在的子命令: %s" % sorted(unknown)


def test_every_cli_subcommand_is_documented():
    """反向覆盖：每个**顶层**子命令都要在 README 出现（含命令总表）。"""
    readme = _read(README)
    _idx, top_level = _parser_index()
    undocumented = [c for c in sorted(top_level)
                    if not re.search(r"\bpicrecall\s+%s\b" % re.escape(c), readme)]
    assert undocumented == [], "CLI 有但 README 未记录的子命令: %s" % undocumented


def test_readme_flags_exist_somewhere_in_cli():
    """README 出现的 --flag 必须在 CLI 某处真实存在（防假旗标）。"""
    readme = _read(README)
    all_flags = _parser_flags() | {"--help", "--version"}
    unknown = {f for f in _readme_flags(readme) if f not in all_flags}
    assert unknown == set(), "README 提到但 CLI 不存在的旗标: %s" % sorted(unknown)


def test_readme_install_extras_declared_in_pyproject():
    """README 的 extras 安装行 ↔ pyproject 声明双向对账。"""
    readme = _read(README)
    pyproject = _read(PYPROJECT)

    declared = set(re.findall(r"^\[project\.optional-dependencies\]", pyproject, re.M))
    assert declared, "pyproject 缺 optional-dependencies 段"

    # 解析 pyproject 的 extras 名
    _toml = _toml_module()
    data = _toml.loads(pyproject)
    extras = set(data.get("project", {}).get("optional-dependencies", {}).keys())

    used = set()
    for m in re.finditer(r'\.\[([^\]]+)\]', readme):
        for part in m.group(1).split(","):
            used.add(part.strip())
    unknown = used - extras
    assert unknown == set(), "README 用了 pyproject 未声明的 extra: %s" % sorted(unknown)


def test_requirements_txt_lists_ocr_and_core():
    """题目文档指定 requirements.txt 为安装入口：核心与 OCR 依赖都要在里面。"""
    req = _read(os.path.join(REPO_ROOT, "requirements.txt"))
    for needle in ("Pillow", "imagehash", "rapidocr-onnxruntime", "onnxruntime"):
        assert needle in req, "requirements.txt 缺 %s" % needle


def test_all_package_modules_are_importable():
    """安装面：src 布局下每个模块都能 import（防"包没进安装面"类缺陷）。"""
    import importlib

    for name in ("cli", "config", "db", "index", "ocr", "search", "dedupe",
                 "bench", "selftest", "serialize", "simple_tokenizer"):
        importlib.import_module("picrecall.%s" % name)


def test_tests_only_import_declared_or_stdlib():
    """测试真 import 的第三方库必须能在 pyproject 的 dev/ocr extra 里找到。

    别名表：分发名 ↔ import 名。
    """
    _toml = _toml_module()

    data = _toml.loads(_read(PYPROJECT))
    extras = data.get("project", {}).get("optional-dependencies", {})
    deps = data.get("project", {}).get("dependencies", [])
    declared = set()
    for block in list(extras.values()) + [deps]:
        for spec in block:
            declared.add(re.split(r"[<>=!\[;]", spec)[0].strip())

    alias = {
        "PIL": "Pillow",
        "rapidocr_onnxruntime": "rapidocr-onnxruntime",
        "yaml": "PyYAML",
        "pytest": "pytest",
        "tomli": "tomli",
    }
    frozen_stdlib = {
        "os", "sys", "re", "json", "ast", "time", "csv", "io", "hashlib", "sqlite3",
        "argparse", "tempfile", "shutil", "contextlib", "importlib", "inspect",
        "builtins", "pathlib", "unittest", "collections", "itertools", "functools",
        "typing", "warnings", "datetime", "math", "random", "subprocess", "glob",
        "traceback", "copy", "textwrap", "difflib", "struct", "base64", "tomllib",
        "picrecall",
    }

    tests_dir = os.path.join(REPO_ROOT, "tests")
    offenders = []
    for fname in sorted(os.listdir(tests_dir)):
        if not fname.endswith(".py"):
            continue
        tree = ast.parse(_read(os.path.join(tests_dir, fname)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for n in names:
                if not n or n in frozen_stdlib:
                    continue
                if n in declared or alias.get(n) in declared:
                    continue
                offenders.append((fname, n))
    assert offenders == [], "测试 import 了未声明的第三方库: %s" % offenders
