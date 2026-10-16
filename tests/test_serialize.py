"""确定性写盘测试（K12）：同输入双跑逐字节一致、LF、尾换行、无 BOM。"""

from picrecall import serialize


def test_json_dump_is_sorted_and_utf8_native():
    text = serialize.dumps_json({"b": 1, "a": "账单"})
    assert text.startswith('{\n  "a"')
    assert "账单" in text          # ensure_ascii=False
    assert "\\u" not in text
    assert text.endswith("\n")


def test_json_write_is_byte_identical_on_rerun(tmp_path):
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    obj = {"z": [3, 1, 2], "a": "中文", "m": {"y": 1, "x": 2}}
    serialize.write_json(p1, obj)
    serialize.write_json(p2, obj)
    assert p1.read_bytes() == p2.read_bytes()


def test_text_write_normalizes_line_endings(tmp_path):
    p = tmp_path / "t.txt"
    serialize.write_text(p, "a\r\nb\rc\n")
    assert p.read_bytes() == b"a\nb\nc\n"


def test_no_bom_and_lf_only(tmp_path):
    p = tmp_path / "t.txt"
    serialize.write_text(p, "账单\n")
    data = p.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data


def test_csv_write_is_deterministic(tmp_path):
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    header = ("a", "b")
    rows = [("1", "账单"), ("2", "x")]
    serialize.write_csv(p1, header, rows)
    serialize.write_csv(p2, header, rows)
    assert p1.read_bytes() == p2.read_bytes()
    assert p1.read_bytes() == "a,b\n1,账单\n2,x\n".encode("utf-8")


def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "out.json"
    serialize.write_json(p, {"k": "v"})
    leftovers = [f for f in tmp_path.iterdir() if f.name.startswith(".picrecall-tmp-")]
    assert leftovers == []
