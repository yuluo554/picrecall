"""模块 2：OCR 识别管线（plan/04 §四）。

纪律：
  - 批量识别 + 失败隔离：单张失败标记状态、可续跑（K5）；
  - 阈值一处定义于 config.OCR_CONF_MIN；
  - 同图重跑 OCR 结果一致方可覆盖入库（K4，run_sig 防陈旧覆盖）；
  - 惰性导入纪律：try/except 包住从 import 到调用完成的整条路径，
    缺依赖走 exit 3 契约（不抛裸异常）。
"""

import hashlib
import json
import os

from . import config
from .db import set_meta, write_txn
from .index import sha256_file
from .search import index_chunks

_ENGINE = None


class MissingDependency(Exception):
    """依赖缺失契约（对应 config.EXIT_MISSING_DEP）。"""


def engine_version():
    try:
        import rapidocr_onnxruntime as m

        return "rapidocr-onnxruntime/%s" % getattr(m, "__version__", "unknown")
    except Exception:
        return "rapidocr-onnxruntime/unknown"


def load_engine():
    """惰性加载 OCR 引擎（整条路径包在 try 内，缺依赖显式契约化）。"""
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR

        _ENGINE = RapidOCR()
    except Exception as exc:  # 含 ImportError 与模型/onnxruntime 初始化失败
        raise MissingDependency(
            "OCR 引擎不可用（%s）。请安装: pip install -r requirements.txt" % exc
        )
    return _ENGINE


def compute_run_sig(file_hash, engine_ver, profile, conf_min):
    """输入签名（K4）：把结果绑定到它的**输入身份**（内容 + 引擎 + 阈值 + 分词 profile）。

    sig 是"结果 ↔ 输入"的凭据：只要输入身份变了，旧结果就作废（不得继续被检索到，
    也不得被当成当前输入的产物落库）。见 `ocr_pending` 的陈旧拒绝分支与
    `index.apply_scan` 的派生行作废。
    """
    payload = "|".join([file_hash or "", engine_ver, profile, "%.6f" % conf_min])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ocr_one(engine, path):
    """识别单张图，返回 (lines, mean_conf)。lines = [{"text","conf"}...]。"""
    result, _elapse = engine(path)
    lines = []
    for item in (result or []):
        text = str(item[1])
        conf = float(item[2])
        lines.append({"text": text, "conf": conf})
    mean_conf = (sum(l["conf"] for l in lines) / len(lines)) if lines else 0.0
    return lines, mean_conf


def ocr_pending(conn, limit=None, retry_failed=False, profile=None, progress=None):
    """对待识别文件跑 OCR，返回统计。

    失败隔离：单张异常 → status=ocr_failed / ocr_tries+=1 / ocr_error 记原因，不中断整批。

    陈旧拒绝（K4）：落库前比对**磁盘内容**与台账记录的输入身份（`files.file_hash`）。
    文件在扫描之后被改动（未重索引）时二者不符 → 本次结果**不落库**（不覆盖），
    标记 `ocr_error` 并留在 pending，报告"输入已变，需重建"。否则会出现
    "结果声称属于旧内容、文本却来自新内容"的错绑。
    """
    profile = profile or config.PROFILE_CHAR
    if retry_failed:
        statuses = ("pending", "ocr_failed")
    else:
        statuses = ("pending",)
    placeholders = ",".join("?" for _ in statuses)
    sql = (
        "SELECT id, path, file_hash, size, mtime_ns, status FROM files WHERE status IN (%s) "
        "ORDER BY path" % placeholders
    )
    rows = conn.execute(sql, statuses).fetchall()
    if limit is not None:
        rows = rows[: int(limit)]

    ok = failed = stale = 0
    engine = None
    for row in rows:
        path = row["path"]
        if not os.path.isfile(path):
            with write_txn(conn):
                conn.execute(
                    "UPDATE files SET status = 'missing' WHERE id = ?", (row["id"],)
                )
            continue
        try:
            if engine is None:
                engine = load_engine()
            lines, mean_conf = ocr_one(engine, path)
        except MissingDependency:
            raise
        except Exception as exc:
            with write_txn(conn):
                conn.execute(
                    "UPDATE files SET status = 'ocr_failed', ocr_tries = ocr_tries + 1, "
                    "ocr_error = ? WHERE id = ?",
                    ("%s: %s" % (type(exc).__name__, exc), row["id"]),
                )
            failed += 1
            continue

        # K4：结果必须绑定到**当前实际输入**。台账记录的 file_hash 是本次识别所依据的
        # 输入身份；磁盘内容若已偏离它（扫描后文件被改动、尚未重索引），本次结果不得落库
        # ——否则会出现"结果声称属于旧内容、文本却来自新内容"的错绑。
        # 探活复用 K2 的快速路径（size+mtime 同即视为未变，不重算 hash）。
        try:
            st = os.stat(path)
            unchanged = (st.st_size == row["size"] and st.st_mtime_ns == row["mtime_ns"])
        except OSError:
            unchanged = False
        file_hash = row["file_hash"] or sha256_file(path)
        if not unchanged:
            disk_hash = sha256_file(path)
            if row["file_hash"] and row["file_hash"] != disk_hash:
                with write_txn(conn):
                    conn.execute(
                        "UPDATE files SET status = 'pending', ocr_error = ? WHERE id = ?",
                        ("输入已变，需重建：磁盘内容与台账 file_hash 不符", row["id"]),
                    )
                stale += 1
                continue
            file_hash = disk_hash

        sig = compute_run_sig(file_hash, engine_version(), profile, config.OCR_CONF_MIN)
        _store_ocr(conn, row["id"], file_hash, lines, mean_conf, sig, profile)
        ok += 1
        if progress:
            progress(ok + failed + stale, len(rows))

    return {"ok": ok, "failed": failed, "stale": stale, "considered": len(rows)}


def _store_ocr(conn, file_id, file_hash, lines, mean_conf, run_sig, profile):
    text = "\n".join(l["text"] for l in lines)
    line_json = json.dumps(
        [{"text": l["text"], "conf": round(l["conf"], 6)} for l in lines],
        ensure_ascii=False,
        sort_keys=True,
    )
    low_conf = sum(1 for l in lines if l["conf"] < config.OCR_CONF_MIN)
    with write_txn(conn):
        conn.execute(
            "INSERT INTO ocr_text(file_id, text, line_json, mean_conf, line_count, engine, run_sig) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(file_id) DO UPDATE SET text=excluded.text, line_json=excluded.line_json, "
            "mean_conf=excluded.mean_conf, line_count=excluded.line_count, "
            "engine=excluded.engine, run_sig=excluded.run_sig",
            (file_id, text, line_json, float(mean_conf), len(lines), engine_version(), run_sig),
        )
        conn.execute(
            "UPDATE files SET file_hash = ?, status = 'indexed', ocr_error = NULL WHERE id = ?",
            (file_hash, file_id),
        )
        set_meta(conn, "low_conf_lines_%d" % file_id, str(low_conf))
    index_chunks(conn, file_id, [l["text"] for l in lines], profile)


def get_ocr_text(conn, file_id):
    row = conn.execute(
        "SELECT text, line_json, mean_conf, line_count, engine, run_sig "
        "FROM ocr_text WHERE file_id = ?",
        (file_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "text": row["text"],
        "lines": json.loads(row["line_json"]),
        "mean_conf": row["mean_conf"],
        "line_count": row["line_count"],
        "engine": row["engine"],
        "run_sig": row["run_sig"],
    }
