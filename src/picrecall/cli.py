"""CLI 编排层（plan/04 §二）。

纪律：
  - 本层只做参数解析与编排，不承载数值口径（一律取 config）；
  - _ensure_utf8_stdio() 覆盖**所有**子命令入口（K15）；
  - 退出码语义按 config 的 0/1/2/3 契约返回，不抛裸异常。
"""

import argparse
import json
import os
import sys

from . import SCHEMA_VERSION, __version__, bench, config, db, dedupe, index, ocr, search, selftest
from .serialize import write_json


def _ensure_utf8_stdio():
    """按 stream.encoding 探针决定是否 reconfigure（中文控制台 cp936 保持不动）。

    注意：本机 `py -X utf8` 只改"我们敲的那条命令"的 stdio，改不了子进程与 CI 的编码通路
    （见验收门）；故入口显式加固，并在 CI 设 PYTHONUTF8=1。
    """
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower()
        if enc in ("cp1252", "ascii", "latin-1", "ansi_x3.4-1968"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _out(args, obj, human_lines):
    """人读/机读双轨输出。"""
    if getattr(args, "json", False):
        print(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for line in human_lines:
            print(line)


def _resolve_db(args, folder=None):
    if args.db:
        return os.path.abspath(args.db)
    if folder:
        return os.path.join(os.path.abspath(folder), config.DB_FILENAME)
    return os.path.abspath(config.DB_FILENAME)


# ── 子命令实现 ──────────────────────────────────────────────────────────

def cmd_index(args):
    folder = args.folder
    if not os.path.isdir(folder):
        print("错误：不是有效文件夹: %s" % folder, file=sys.stderr)
        return config.EXIT_USAGE
    db_path = _resolve_db(args, folder)
    conn = db.connect(db_path)
    try:
        entries = index.scan_folder(folder)
        result = index.apply_scan(conn, entries)
        profile = args.profile or config.PROFILE_CHAR
        db.set_meta(conn, "tokenizer_profile", profile)
        db.set_meta(conn, "source_folder", os.path.abspath(folder))
        conn.commit()
        stats = index.index_stats(conn)
    finally:
        conn.close()

    payload = {"db": db_path, "scan": result, "stats": stats}
    human = [
        "索引库: %s" % db_path,
        "扫描到 %d 个图片文件（新增 %d / 变更 %d / 未变 %d / 失效 %d）"
        % (len(entries), result["added"], result["changed"], result["unchanged"], result["missing"]),
        "待识别: %d 个（下一步: picrecall ocr）" % stats["by_status"].get("pending", 0),
    ]
    _out(args, payload, human)
    return config.EXIT_OK


def cmd_ocr(args):
    db_path = _resolve_db(args)
    if not os.path.isfile(db_path):
        print("错误：索引库不存在: %s（请先运行 picrecall index）" % db_path, file=sys.stderr)
        return config.EXIT_USAGE
    conn = db.connect(db_path)
    try:
        profile = args.profile or db.get_meta(conn, "tokenizer_profile", config.PROFILE_CHAR)
        try:
            report = ocr.ocr_pending(conn, limit=args.limit, retry_failed=args.retry_failed,
                                     profile=profile)
        except ocr.MissingDependency as exc:
            print("依赖缺失：%s" % exc, file=sys.stderr)
            return config.EXIT_MISSING_DEP
        stats = index.index_stats(conn)
    finally:
        conn.close()

    payload = {"db": db_path, "ocr": report, "stats": stats}
    human = [
        "识别完成：成功 %d / 失败 %d / 处理 %d" % (report["ok"], report["failed"], report["considered"]),
    ]
    if report.get("stale"):
        human.append("输入已变、未落库 %d 项（内容在扫描后改动）：请先重跑 picrecall index 再识别"
                     % report["stale"])
    if report["failed"]:
        human.append("有失败项：可运行 picrecall ocr --retry-failed 续跑")
    _out(args, payload, human)
    # 有失败项/陈旧项 = 检出问题（exit 1，非跑挂）
    return config.EXIT_FINDINGS if (report["failed"] or report.get("stale")) else config.EXIT_OK


def cmd_search(args):
    db_path = _resolve_db(args)
    if not os.path.isfile(db_path):
        print("错误：索引库不存在: %s" % db_path, file=sys.stderr)
        return config.EXIT_USAGE
    if args.limit is not None and args.limit <= 0:
        print("错误：--limit 必须为正整数", file=sys.stderr)
        return config.EXIT_USAGE
    conn = db.connect(db_path)
    try:
        try:
            hits = search.search(conn, args.query, limit=args.limit, profile=args.profile)
        except ValueError as exc:
            print("错误：%s" % exc, file=sys.stderr)
            return config.EXIT_USAGE
    finally:
        conn.close()

    payload = {"query": args.query, "count": len(hits), "hits": hits}
    human = ["命中 %d 条：%s" % (len(hits), args.query)]
    for h in hits:
        human.append("%s:%d  %s" % (h["path"], h["line_no"] + 1, h["snippet"]))
    if not hits:
        human.append("（无命中。可换更短的查询词；中文为子串匹配）")
    _out(args, payload, human)
    return config.EXIT_OK  # 零命中 = 合法空结果


def cmd_dedupe(args):
    db_path = _resolve_db(args)
    if not os.path.isfile(db_path):
        print("错误：索引库不存在: %s" % db_path, file=sys.stderr)
        return config.EXIT_USAGE
    if args.threshold is not None and args.threshold < 0:
        print("错误：--threshold 不能为负", file=sys.stderr)
        return config.EXIT_USAGE
    conn = db.connect(db_path)
    try:
        groups = dedupe.phash_groups(conn, threshold=args.threshold)
    finally:
        conn.close()

    out_path = args.out
    if groups and out_path:
        dedupe.write_keep_suggestions(groups, out_path)

    payload = {
        "db": db_path,
        "groups": [
            {"group_id": g["group_id"], "representative": g["representative"]["path"],
             "members": [m["path"] for m in g["members"]]}
            for g in groups
        ],
        "suggestion_file": out_path if (groups and out_path) else None,
        "note": "只输出保留建议，未删除任何文件",
    }
    human = ["发现 %d 组相似图（默认只读，未删除任何文件）" % len(groups)]
    if groups and out_path:
        human.append("保留建议清单: %s" % out_path)
    for g in groups:
        human.append("  组 %d: 建议保留 %s（%d 张相似）"
                     % (g["group_id"], g["representative"]["path"], len(g["members"])))
    _out(args, payload, human)
    return config.EXIT_FINDINGS if groups else config.EXIT_OK


def cmd_stats(args):
    db_path = _resolve_db(args)
    if not os.path.isfile(db_path):
        print("错误：索引库不存在: %s" % db_path, file=sys.stderr)
        return config.EXIT_USAGE
    conn = db.connect(db_path)
    try:
        stats = index.index_stats(conn)
        profile = db.get_meta(conn, "tokenizer_profile", config.PROFILE_CHAR)
        folder = db.get_meta(conn, "source_folder", "")
    finally:
        conn.close()
    payload = {"db": db_path, "profile": profile, "source_folder": folder, "stats": stats}
    human = [
        "索引库: %s" % db_path,
        "来源文件夹: %s" % (folder or "(未记录)"),
        "分词 profile: %s" % profile,
        "文件总数: %d（已识别 %d）" % (stats["total_files"], stats["ocr_done"]),
        "状态分布: %s" % json.dumps(stats["by_status"], ensure_ascii=False, sort_keys=True),
    ]
    _out(args, payload, human)
    return config.EXIT_OK


def cmd_bench_gen(args):
    # `--data` 省略时取默认数据目录（仓库 data/）——这里**必须**显式解析出默认值：
    # 直接把 args.data 往下传会让 os.path.join(None, "synthetic") 抛裸 TypeError
    # （M5 实测：README §其它命令 的三条 `bench gen` 全都 exit 1 裸崩，而非声明的 exit 2）。
    try:
        data_dir = bench.require_data_dir(args.data)
    except FileNotFoundError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return config.EXIT_USAGE
    if args.dupes:
        # 近似重复族子集（M2）：默认落到 data/synthetic_dupes，与主集分开，互不影响。
        # `--dupes` 与 `--check` 语义不兼容（`--check` 是主集的再生成对账），
        # 组合时显式报用法错误，而不是**静默忽略**用户给的一个旗标。
        if args.check:
            print("错误：--dupes 与 --check 不能同时使用（--check 只对主集做再生成对账）",
                  file=sys.stderr)
            return config.EXIT_USAGE
        out_dir = args.out or os.path.join(data_dir, "synthetic_dupes")
        try:
            manifest = bench.gen_dupes(out_dir, data_dir=data_dir, seed=args.seed,
                                       count=args.count)
        except (FileNotFoundError, ValueError) as exc:
            print("错误：%s" % exc, file=sys.stderr)
            return config.EXIT_USAGE
        payload = {"manifest": manifest, "out_dir": os.path.abspath(out_dir), "kind": "dupes"}
        _out(args, payload, ["近似重复族合成集已生成: %s" % os.path.abspath(out_dir),
                            "真值 manifest: %s" % manifest])
        return config.EXIT_OK

    out_dir = args.out or os.path.join(data_dir, "synthetic")
    try:
        if args.check:
            result = bench.check_generated(out_dir, data_dir=data_dir, seed=args.seed,
                                           count=args.count)
            if result["ok"]:
                note = result.get("note")
                msg = "再生成一致（%d 张图，sha256 逐一比对通过）" % result["images"]
                if note:
                    msg = "再生成一致（%d 张图；%s）" % (result["images"], note)
                _out(args, result, [msg])
                return config.EXIT_OK
            print("基准漂移：%s" % result["reason"], file=sys.stderr)
            if result.get("diff"):
                print("  定位：%s" % result["diff"], file=sys.stderr)
            return config.EXIT_FINDINGS
        manifest = bench.gen_synthetic(out_dir, data_dir=data_dir, seed=args.seed,
                                       count=args.count)
    except (FileNotFoundError, ValueError) as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return config.EXIT_USAGE

    payload = {"manifest": manifest, "out_dir": os.path.abspath(out_dir)}
    _out(args, payload, ["合成截图集已生成: %s" % os.path.abspath(out_dir),
                         "真值 manifest: %s" % manifest])
    return config.EXIT_OK


def cmd_bench_run(args):
    db_path = _resolve_db(args)
    if not os.path.isfile(db_path):
        print("错误：索引库不存在: %s（请先 index + ocr）" % db_path, file=sys.stderr)
        return config.EXIT_USAGE
    conn = db.connect(db_path)
    try:
        try:
            report = bench.run_bench(conn, data_dir=args.data, inject_defect=args.inject_defect)
        except FileNotFoundError as exc:
            # 数据目录/manifest 缺席属用法与输入错误（K9 → exit 2），不是"检出问题"，
            # 更不能裸抛异常（M5 实测：裸 FileNotFoundError 会以 traceback + exit 1 收场）。
            print("错误：%s" % exc, file=sys.stderr)
            return config.EXIT_USAGE
        except ValueError as exc:
            # 指向非对账对象的数据目录（如近似重复族子集 manifest，M6）同属用法错误。
            print("错误：%s" % exc, file=sys.stderr)
            return config.EXIT_USAGE
    finally:
        conn.close()

    eff = report.get("effective_thresholds", report["thresholds"])
    rules = report.get("rules", {})
    payload = report
    human = [
        "分词 profile: %s（生效门槛按 profile 取，M4/D-22）" % report.get("profile", "?"),
        "OCR 行识别率: %.4f（门槛 %.2f，%d/%d 行；严格单条口径 %.4f）"
        % (report["ocr"]["recall"], eff["ocr_line_recall"],
           report["ocr"]["detected_lines"], report["ocr"]["total_lines"],
           report["ocr"].get("recall_strict_single_line", 0.0)),
        "检索命中率: %.4f（门槛 %.2f，%d/%d 查询；误召回 %d）"
        % (report["search"]["recall"], eff["query_recall"],
           report["search"]["recalled_queries"], report["search"]["total_queries"],
           report["search"]["false_positives"]),
        "样本驱动层: %s" % ("达标" if report.get("sample_passed") else "未达标"),
    ]
    if rules:
        human.append(
            "规则驱动层（不读 manifest）: %s（%d 项探针，%s）"
            % ("达标" if rules.get("passed") else "未达标", len(rules.get("probes", [])),
               "OCR 可用" if rules.get("available") else "OCR 不可用，OCR 类探针降级"))
        for p in rules.get("probes", []):
            human.append("  [%s] %s: %s"
                         % ("ok" if p["ok"] else "!!", p["name"], p["detail"]))
    human.append("结论: %s" % ("达标" if report["passed"] else "未达标"))
    _out(args, payload, human)
    return config.EXIT_OK if report["passed"] else config.EXIT_FINDINGS


def cmd_selftest(args):
    result = selftest.run_selftest(require_ocr=args.require_ocr)
    human = ["picrecall %s（schema %s，Python %s）"
             % (result["version"], result["schema_version"], result["python"])]
    for c in result["checks"]:
        human.append("  [%s] %s: %s" % ("ok" if c["ok"] else "!!", c["name"], c["detail"]))
    for p in result["config_problems"]:
        human.append("  [!!] 口径: %s" % p)
    if not result["ocr_available"]:
        human.append("  提示：OCR 引擎不可用，index/search/dedupe 仍可用；"
                     "装全依赖请 pip install -r requirements.txt")
    human.append("自检结论: %s" % ("通过" if result["exit_code"] == 0 else "有问题"))
    _out(args, result, human)
    return result["exit_code"]


# ── 参数解析 ────────────────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        prog="picrecall",
        description="本地截图文字检索库：对截图文件夹做 OCR 索引，按图中文字秒级搜回那张图"
                    "（纯本地、零上传、默认只读）",
    )
    p.add_argument("--version", action="version", version="picrecall %s" % __version__)
    sub = p.add_subparsers(dest="command", metavar="<command>")

    sp = sub.add_parser("index", help="建/更新索引（扫描文件夹 + 变更检测）")
    sp.add_argument("folder", help="截图文件夹路径（递归扫描）")
    sp.add_argument("--db", help="索引库路径（默认 <folder>/.picrecall.db）")
    sp.add_argument("--profile", choices=[config.PROFILE_CHAR, config.PROFILE_SIMPLE],
                    help="分词 profile（默认 char 兜底路径）")
    sp.add_argument("--json", action="store_true", help="机读 JSON 输出")
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("ocr", help="对新增/变更图片跑 OCR 识别")
    sp.add_argument("--db", help="索引库路径（默认 ./.picrecall.db）")
    sp.add_argument("--limit", type=int, help="本次最多处理张数")
    sp.add_argument("--retry-failed", action="store_true", help="把之前失败的项重新纳入待办")
    sp.add_argument("--profile", choices=[config.PROFILE_CHAR, config.PROFILE_SIMPLE],
                    help="分词 profile")
    sp.add_argument("--json", action="store_true", help="机读 JSON 输出")
    sp.set_defaults(func=cmd_ocr)

    sp = sub.add_parser("search", help="按图中文字检索")
    sp.add_argument("query", help="查询词（中文/英文）")
    sp.add_argument("--db", help="索引库路径（默认 ./.picrecall.db）")
    sp.add_argument("--limit", type=int, help="最多返回条数")
    sp.add_argument("--profile", choices=[config.PROFILE_CHAR, config.PROFILE_SIMPLE],
                    help="分词 profile（须与索引库一致）")
    sp.add_argument("--json", action="store_true", help="机读 JSON 输出")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("dedupe", help="相似截图分组 + 保留建议清单（默认只读，不删文件）")
    sp.add_argument("--db", help="索引库路径（默认 ./.picrecall.db）")
    sp.add_argument("--out", help="保留建议清单 CSV 输出路径")
    sp.add_argument("--threshold", type=int, help="pHash 汉明距离阈值（默认取 config）")
    sp.add_argument("--json", action="store_true", help="机读 JSON 输出")
    sp.set_defaults(func=cmd_dedupe)

    sp = sub.add_parser("stats", help="索引库状态速览")
    sp.add_argument("--db", help="索引库路径（默认 ./.picrecall.db）")
    sp.add_argument("--json", action="store_true", help="机读 JSON 输出")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("bench", help="真值基准（生成合成集 / 对账）")
    bsub = sp.add_subparsers(dest="bench_command", metavar="<gen|run>")
    bp = bsub.add_parser("gen", help="生成合成截图集 + manifest 真值")
    bp.add_argument("--out", help="输出目录（默认 <data>/synthetic）")
    bp.add_argument("--data", help="数据目录（含白名单；默认仓库 data/）")
    bp.add_argument("--seed", type=int, help="固定随机种子（默认取 config）")
    bp.add_argument("--count", type=int, help="图片数量（默认取 config）")
    bp.add_argument("--dupes", action="store_true",
                    help="生成近似重复族子集（供 dedupe 端到端真样例；与主集分开）")
    bp.add_argument("--check", action="store_true", help="再生成一致性校验（不覆盖）")
    bp.add_argument("--json", action="store_true", help="机读 JSON 输出")
    bp.set_defaults(func=cmd_bench_gen)

    bp = bsub.add_parser("run", help="真值对账（识别率 + 检索命中率）")
    bp.add_argument("--db", help="索引库路径（默认 ./.picrecall.db）")
    bp.add_argument("--data", help="数据目录（默认仓库 data/）")
    bp.add_argument("--inject-defect",
                    choices=["ocr_drop", "search_drop"] + list(bench.RULE_INJECT_DEFECTS),
                    help="注入缺陷（验证基准可证伪，必打红）：样本层 ocr_drop/search_drop，"
                         "规则层 rule_blank_always_true/rule_bound_ignored")
    bp.add_argument("--json", action="store_true", help="机读 JSON 输出")
    bp.set_defaults(func=cmd_bench_run)

    sp = sub.add_parser("selftest", help="冻结态自检（依赖/口径探活）")
    sp.add_argument("--require-ocr", action="store_true", help="OCR 引擎缺席即视为失败")
    sp.add_argument("--json", action="store_true", help="机读 JSON 输出")
    sp.set_defaults(func=cmd_selftest)

    return p


def main(argv=None):
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return config.EXIT_USAGE
    if args.command == "bench" and not getattr(args, "bench_command", None):
        print("错误：bench 需要子命令 gen 或 run", file=sys.stderr)
        return config.EXIT_USAGE
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
