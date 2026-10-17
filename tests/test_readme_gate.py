"""README ↔ CLI 反射对账门（验收门"测试面=安装面=README 指令面"）。

三面：
  ① README 里出现的每个 `picrecall <sub>` 命令与 `--flag` 都必须在 CLI 里真实存在；
  ② CLI 的每个子命令都必须在 README 命令总表里被提及（防"文档漏写可用命令"）；
  ③ README 快速开始的安装命令 extras 与 pyproject 声明双向对账。

变异验证：README 里加一个假旗标 → 本测试必须变红。
"""

import ast
import os
import re
import sys

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
    """README 里**属于 picrecall 调用**的旗标。

    判据要按行分域，不能整篇一把抓：README 的 shell 代码块里还有别的命令
    （`python -m pip install --upgrade pip`），把它们的旗标也算进来会得到
    "pip 的 --upgrade 不是 picrecall 旗标"这种**假红**（M5 实测踩到）。

    规则：围栏代码块内**只看调用了 picrecall 的行**；代码块外的正文照旧全文扫
    （正文里提到 `--db` 之类本来就是在说 picrecall）。这样既排除异域旗标，
    又保住"README 里给 picrecall 加个假旗标 → 必红"的牙齿。
    """
    flags = set()
    for block in re.finditer(r"```[a-z]*\n(.*?)```", readme, re.S):
        for line in block.group(1).splitlines():
            if re.search(r"\bpicrecall\b", line):
                flags |= set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]+)", line))
    prose = re.sub(r"```[a-z]*\n.*?```", "\n", readme, flags=re.S)
    flags |= set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]+)", prose))
    return flags


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


def test_requirements_txt_installs_the_project_itself():
    """`pip install -r requirements.txt` 必须**连本项目一起装**（M5 实测缺陷）。

    只列第三方依赖时，装完既没有 `picrecall` 命令、`python -m picrecall` 也报
    ModuleNotFoundError——题目文档 §四 ① 的"装完即可三条命令闭环"不成立。
    故该文件必须含一行对**本仓库自身**的引用（`-e .`），且该引用要真实指向含
    pyproject.toml 的目录（不是写个字符串糊弄）。

    变异：删掉 `-e .` 一行 → 本测试必红。
    """
    req_path = os.path.join(REPO_ROOT, "requirements.txt")
    refs = []
    for raw in _read(req_path).splitlines():
        line = raw.split("#", 1)[0].strip()
        if re.match(r"^(?:-e|--editable)\s+\./?$", line) or line == ".":
            refs.append(line)
    assert refs, ("requirements.txt 未自指本项目（缺 `-e .`）：装完不会有 picrecall 命令，"
                  "也不会装上包本身")

    for ref in refs:
        target = re.sub(r"^(?:-e|--editable)\s+", "", ref).strip() or "."
        resolved = os.path.abspath(os.path.join(REPO_ROOT, target))
        assert os.path.isfile(os.path.join(resolved, "pyproject.toml")), (
            "requirements.txt 的自指 %r 指向的目录不含 pyproject.toml: %s" % (ref, resolved))


# ── M5：README 指令面"照抄能跑"（安装面 = 指令面）────────────────────────────

QUICKSTART_HEADING = "## 快速开始"


def _quickstart_commands(readme):
    """抽出 README §快速开始 代码块里的 `picrecall ...` 调用（逐行原文）。"""
    start = readme.index(QUICKSTART_HEADING)
    m = re.search(r"```bash\n(.*?)```", readme[start:], re.S)
    assert m, "README 快速开始代码块缺失"
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip().startswith("picrecall ")]


def test_readme_quickstart_block_is_present():
    cmds = _quickstart_commands(_read(README))
    assert len(cmds) == 4, "快速开始应给出四条命令，实得 %d: %s" % (len(cmds), cmds)


def test_readme_quickstart_commands_share_one_db():
    """四条命令必须指向**同一个**索引库（缺省时 index 写进被扫描文件夹、其余读当前目录）。

    M5 实测缺陷：README 原文的 `index "<folder>"` 与随后的裸 `ocr` 不在同一处，
    照抄第二条即得"索引库不存在"（exit 2）。本测试把"同一库"这条不变量锁住。
    """
    cmds = _quickstart_commands(_read(README))
    dbs = set()
    for cmd in cmds:
        m = re.search(r"--db\s+(\S+)", cmd)
        dbs.add(m.group(1) if m else None)
    assert len(dbs) == 1, "快速开始各命令的 --db 不一致: %s" % sorted(map(str, dbs))
    assert None not in dbs, "快速开始应显式传 --db（缺省时各命令落点不同）"


def test_readme_quickstart_runs_end_to_end(tmp_path):
    """把快速开始**逐条真跑**（子进程）：不得有任何一条以 exit 2 收场、不得有裸 traceback。

    这是"安装面 = 指令面"的实测门：静态对账（命令/旗标是否存在）挡不住
    "命令存在但照抄跑不通"这类缺陷——M5 实测的 `bench gen` 裸 TypeError 与
    `ocr` 找不到库都属于此类。OCR 引擎缺席时 `ocr` 允许 exit 3（依赖契约）。
    """
    import subprocess

    from PIL import Image

    cmds = _quickstart_commands(_read(README))
    folder = tmp_path / "screenshots"
    folder.mkdir()
    Image.new("RGB", (320, 90), "white").save(str(folder / "shot_0.png"))
    Image.new("RGB", (320, 90), "gray").save(str(folder / "shot_1.png"))

    db_path = tmp_path / "shots.db"
    csv_path = tmp_path / "keep-suggestions.csv"
    # 注意：`str.split()` 不认识引号，命令行里的 `"/path/..."` 会带着引号成为一个整体
    # token，故替换值取**不带引号**的裸路径（否则 argv 里会多出字面引号）。
    subst = {
        '"/path/to/your/screenshots"': str(folder),
        "shots.db": str(db_path),
        "keep-suggestions.csv": str(csv_path),
    }

    env = dict(os.environ, PYTHONUTF8="1")
    results = []
    for cmd in cmds:
        argv = [sys.executable, "-m", "picrecall"] + cmd.split()[1:]
        argv = [subst.get(tok, tok) for tok in argv]
        proc = subprocess.run(argv, cwd=str(tmp_path), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.stdout.decode("utf-8", "replace")
        results.append((cmd, proc.returncode, out))

    codes = [c for _, c, _ in results]
    assert 2 not in codes, "快速开始有命令以 exit 2（用法/输入错误）收场:\n%s" % (
        "\n".join("%s -> exit %d\n%s" % (c, n, o) for c, n, o in results))
    for cmd, code, out in results:
        assert "Traceback" not in out, "快速开始命令裸崩:\n%s -> exit %d\n%s" % (cmd, code, out)

    assert codes[0] == 0, "建索引应 exit 0，实得 %d" % codes[0]
    assert db_path.is_file(), "建索引后索引库不在四条命令共同指向的位置: %s" % db_path
    assert codes[1] in (0, 1, 3), "ocr 退出码越界: %d" % codes[1]
    assert codes[2] == 0, "检索应 exit 0（零命中也是合法空结果），实得 %d" % codes[2]
    assert codes[3] in (0, 1), "dedupe 退出码越界: %d" % codes[3]


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
