#!/usr/bin/env python
"""数据资产台账生成器（plan/05 §六）。

台账是**生成物**：从 data/ 资产复算 sha256 重建，**禁手改**。
改数据后跑本脚本重建；CI/自检可跑 `--check` 核验台账与现状一致（防手改漂移）。

用法：
    python tools/update_data_ledger.py                 # 重建 data/LEDGER.md
    python tools/update_data_ledger.py --check         # 只核验，不一致则 exit 1
    python tools/update_data_ledger.py --out PATH      # 指定输出（默认 data/LEDGER.md）

K15：本脚本是"可打印入口"，入口即调 cli._ensure_utf8_stdio()（中文控制台守卫）。
"""

import argparse
import hashlib
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from picrecall.cli import _ensure_utf8_stdio  # noqa: E402  (K15：入口编码守卫)
from picrecall.serialize import write_text  # noqa: E402  (写盘单点：LF + 无 BOM + 原子写)

DEFAULT_OUT = os.path.join(REPO_ROOT, "data", "LEDGER.md")
DATA_DIR = os.path.join(REPO_ROOT, "data")

# 入台账的资产（相对仓库根的路径 → 登记元数据）。
# "来源/许可/重建命令"必须逐份写明，不许留空——台账的意义就在这里。
ASSETS = [
    {
        "path": "data/whitelist_texts.txt",
        "kind": "白名单文本集（合成图渲染素材源；假值登记处）",
        "source": "自制（本项目编写；号码/单号一律假值）",
        "license": "MIT（本项目）",
        "rebuild": "手工维护（内容变更后跑本脚本重建台账）",
        "privacy": "无真实个人信息；假号段 19900000000 类，假单号已登记于本文件",
    },
    {
        "path": "data/synthetic/manifest.json",
        "kind": "合成截图集真值 manifest（图→文本→应命中词→版式→指纹）",
        "source": "生成器产出（picrecall.bench.gen_synthetic，seed=20261016，count=60）",
        "license": "MIT（本项目）",
        "rebuild": "python -m picrecall bench gen --data data --out data/synthetic",
        "privacy": "渲染文本全部来自白名单（假值）；不含真实截图",
    },
    {
        "path": "data/synthetic_dupes/manifest.json",
        "kind": "近似重复族真值 manifest（dedupe 端到端真样例：族→成员→应同组）",
        "source": "生成器产出（picrecall.bench.gen_dupes，seed=20261017，count=6 族 × 3 成员）",
        "license": "MIT（本项目）",
        "rebuild": "python -m picrecall bench gen --dupes --data data --out data/synthetic_dupes",
        "privacy": "渲染文本全部来自白名单（假值）；不含真实截图",
    },
    {
        "path": "data/schema_notes.md",
        "kind": "索引库 schema 与迁移口径（**只引用不复述** DDL；真源在 db.SCHEMA_SQL）",
        "source": "手工（据 db.py/__init__.py 实况编写）",
        "license": "MIT（本项目）",
        "rebuild": "手工维护（schema 变更后同步更新）",
        "privacy": "无个人数据",
    },
    {
        "path": "data/README.md",
        "kind": "依据查证 + 数据源可获取性 + 合成数据纪律",
        "source": "手工（含 gh api 实测记录）",
        "license": "MIT（本项目）",
        "rebuild": "手工维护",
        "privacy": "无个人数据",
    },
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _extra_facts(rel):
    """对特定资产补记可核验事实（不是手抄，是运行时实算）。"""
    abs_path = os.path.join(REPO_ROOT, rel)
    facts = []
    if rel == "data/whitelist_texts.txt":
        with open(abs_path, "r", encoding="utf-8") as fh:
            lines = [s.strip() for s in fh if s.strip() and not s.strip().startswith("#")]
        facts.append("条目数（非注释行）: %d" % len(lines))
    elif rel == "data/synthetic/manifest.json":
        import json

        with open(abs_path, "r", encoding="utf-8") as fh:
            m = json.load(fh)
        facts.append("图片数: %s" % m.get("image_count"))
        facts.append("seed: %s" % m.get("seed"))
        facts.append("schema: %s" % m.get("schema"))
        facts.append("门槛: %s" % json.dumps(m.get("thresholds"), ensure_ascii=False, sort_keys=True))
        # 图片本体不入 git（可由 seed 位级重建）：台账只登记 manifest 声明值。
        # 不登记"目录内实际图片数"——那是环境依赖事实（作者机器有图片、干净 clone 没有），
        # 写进去会让台账随环境漂移（M6 干净 clone 实测：--check 在 clone 必红）。
    elif rel == "data/synthetic_dupes/manifest.json":
        import json

        with open(abs_path, "r", encoding="utf-8") as fh:
            m = json.load(fh)
        facts.append("族数: %s" % m.get("family_count"))
        facts.append("每族成员数: %s" % m.get("members_per_family"))
        facts.append("图片数: %s" % m.get("image_count"))
        facts.append("seed: %s" % m.get("seed"))
        facts.append("schema: %s" % m.get("schema"))
        facts.append("门槛: %s" % json.dumps(m.get("thresholds"), ensure_ascii=False, sort_keys=True))
        # 同上：不登记环境依赖的"目录内实际图片数"（M6 干净 clone 实测教训）
    elif rel == "data/schema_notes.md":
        with open(abs_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        facts.append("是否引用真源 db.SCHEMA_SQL: %s"
                     % ("是" if "SCHEMA_SQL" in text else "否（不合纪律）"))
        # 只允许**正文行内引用**（如 `CREATE TABLE IF NOT EXISTS` 这类说明），
        # 不允许**代码块里复述 DDL**——后者才是"第二份 schema 定义"。
        ddl_blocks = 0
        in_fence = False
        for line in text.splitlines():
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence and line.strip().upper().startswith("CREATE TABLE"):
                ddl_blocks += 1
        facts.append("代码块内 DDL 复述行数（应为 0）: %d" % ddl_blocks)
    return facts


def build_ledger():
    rows = []
    for asset in ASSETS:
        abs_path = os.path.join(REPO_ROOT, asset["path"])
        if not os.path.isfile(abs_path):
            rows.append({"asset": asset, "missing": True})
            continue
        rows.append({
            "asset": asset,
            "missing": False,
            "sha256": sha256_file(abs_path),
            "size": os.path.getsize(abs_path),
            "facts": _extra_facts(asset["path"]),
        })

    out = []
    out.append("# 数据资产台账（生成物 · 禁手改）")
    out.append("")
    out.append("> **本文件由 `tools/update_data_ledger.py` 从 `data/` 资产复算生成。**")
    out.append("> 改数据后请跑该脚本重建，**不要手改本文件**——手改会导致台账与现状漂移。")
    out.append("> 核验：`python tools/update_data_ledger.py --check`（不一致 exit 1）。")
    out.append("> 纪律出处：plan/05 §六；数据来源与隐私口径见 data/README.md。")
    out.append("")
    out.append("| 资产 | 类型 | 来源 | 许可 | sha256 | 大小(B) |")
    out.append("|---|---|---|---|---|---|")
    for r in rows:
        a = r["asset"]
        if r["missing"]:
            out.append("| `%s` | %s | %s | %s | **缺失** | — |"
                       % (a["path"], a["kind"], a["source"], a["license"]))
            continue
        out.append("| `%s` | %s | %s | %s | `%s` | %d |"
                   % (a["path"], a["kind"], a["source"], a["license"], r["sha256"], r["size"]))
    out.append("")
    out.append("## 重建命令（逐份）")
    out.append("")
    out.append("| 资产 | 重建命令 |")
    out.append("|---|---|")
    for r in rows:
        a = r["asset"]
        out.append("| `%s` | `%s` |" % (a["path"], a["rebuild"]))
    out.append("")
    out.append("## 隐私口径（逐份）")
    out.append("")
    out.append("| 资产 | 隐私说明 |")
    out.append("|---|---|")
    for r in rows:
        a = r["asset"]
        out.append("| `%s` | %s |" % (a["path"], a["privacy"]))
    out.append("")
    out.append("## 运行时实算事实（非手抄）")
    out.append("")
    for r in rows:
        a = r["asset"]
        if r["missing"]:
            continue
        out.append("- **`%s`**" % a["path"])
        for f in r["facts"]:
            out.append("  - %s" % f)
    out.append("")
    out.append("## 不入 git 的产物（登记以便对账）")
    out.append("")
    out.append("| 产物 | 为何不入 git | 重建方式 |")
    out.append("|---|---|---|")
    out.append("| `data/synthetic/*.png` | 大体积且可位级重建（seed 固定）；manifest 已登记 sha256 与 pixel_sha256 | "
               "`python -m picrecall bench gen --data data --out data/synthetic` |")
    out.append("| `data/synthetic_dupes/*.{png,bmp}` | 同上（近似重复族样例；manifest 已登记族与指纹） | "
               "`python -m picrecall bench gen --dupes --data data --out data/synthetic_dupes` |")
    out.append("| `*.db` / `.picrecall.db` | 索引库含用户截图 OCR 结果（隐私红线） | 运行时产出 |")
    out.append("")
    return "\n".join(out) + "\n"


def main(argv=None):
    _ensure_utf8_stdio()  # K15
    ap = argparse.ArgumentParser(description="数据资产台账生成/核验（生成物，禁手改）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="台账输出路径（默认 data/LEDGER.md）")
    ap.add_argument("--check", action="store_true", help="只核验，不一致则 exit 1")
    args = ap.parse_args(argv)

    content = build_ledger()

    if args.check:
        if not os.path.isfile(args.out):
            print("台账缺失: %s（请先运行本脚本重建）" % args.out, file=sys.stderr)
            return 1
        with open(args.out, "r", encoding="utf-8") as fh:
            current = fh.read()
        if current != content:
            print("台账与现状不一致（疑似手改或数据已变）：%s" % args.out, file=sys.stderr)
            print("  请运行: python tools/update_data_ledger.py", file=sys.stderr)
            return 1
        print("台账一致: %s" % args.out)
        return 0

    write_text(args.out, content)
    print("台账已重建: %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
