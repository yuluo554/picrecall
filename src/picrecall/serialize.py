"""确定性写盘单点（K12）。

所有子命令的产物写盘一律经本模块——别让各子命令各写各的 open()+json.dump()。
序列化参数作为冻结契约：
    json.dumps(sort_keys=True, ensure_ascii=False, indent=2) + LF + 结尾换行

`ensure_ascii=False` 是中文项目的必选项（默认 True 会把中文转 \\uXXXX，diff 不可读）。
原子写：写临时文件再 os.replace，防中断留下半个产物。
"""

import csv
import io
import json
import os
import tempfile


def _atomic_write_bytes(path, data: bytes) -> str:
    path = os.path.abspath(path)
    parent = os.path.dirname(path) or "."
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".picrecall-tmp-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def dumps_json(obj) -> str:
    """冻结的 JSON 序列化（唯一口径）。"""
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2)
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_json(path, obj) -> str:
    return _atomic_write_bytes(path, dumps_json(obj).encode("utf-8"))


def write_text(path, text) -> str:
    """文本落盘：LF 归一 + 结尾换行 + UTF-8 无 BOM。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return _atomic_write_bytes(path, text.encode("utf-8"))


def dumps_csv(header, rows) -> str:
    """冻结的 CSV 序列化：LF 行尾、不写 BOM、字段按给定顺序。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(list(header))
    for row in rows:
        writer.writerow(list(row))
    return buf.getvalue()


def write_csv(path, header, rows) -> str:
    return write_text(path, dumps_csv(header, rows))
