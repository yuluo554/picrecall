"""分词双路径测试（plan/03 §三）。

关键：短中文查询（2 字）必须命中——这是 trigram 兜底被否掉的直接原因，
也是 char 兜底路径存在的理由。
"""

import pytest

from picrecall import config
from picrecall.search import make_match_query, segment


@pytest.mark.parametrize("text,expect_tokens", [
    ("本月账单已生成", ["本", "月", "账", "单", "已", "生", "成"]),
    ("config error", ["config", "error"]),
    ("订单号 19900000001", ["订", "单", "号", "19900000001"]),
])
def test_char_segment_splits_cjk_and_keeps_ascii(text, expect_tokens):
    assert segment(text, config.PROFILE_CHAR).split() == expect_tokens


def test_short_chinese_query_matches_phrase():
    """2 字中文查询的 phrase 表达式（这是 trigram 做不到的场景）。"""
    m = make_match_query("账单", config.PROFILE_CHAR)
    assert m == '"账 单"'


def test_ascii_query_is_single_token():
    assert make_match_query("timeout", config.PROFILE_CHAR) == '"timeout"'


def test_empty_query_returns_none():
    assert make_match_query("   ", config.PROFILE_CHAR) is None


def test_unknown_profile_raises():
    with pytest.raises(ValueError):
        segment("账单", "nope")


def test_simple_profile_unavailable_is_explicit(monkeypatch):
    """主路径不可用必须显式报错，不静默回落（不冒充可用）。

    M1 起 simple_segment 已接线（libsimple DLL + cppjieba 词典齐备时可用）。
    本测试锁的是**不可用分支**：把定位函数打成"找不到"→ 必须抛 SimpleUnavailable。
    """
    from picrecall import simple_tokenizer

    simple_tokenizer._reset_cache()
    monkeypatch.setattr(simple_tokenizer, "find_library", lambda: None)
    with pytest.raises(simple_tokenizer.SimpleUnavailable):
        segment("账单", config.PROFILE_SIMPLE)


def test_simple_profile_missing_dict_is_explicit(monkeypatch, tmp_path):
    """DLL 在但词典缺失 → 也必须显式 SimpleUnavailable，绝不把进程交给 cppjieba 中止。

    实测（M1）：jieba_query() 在词典缺失时是**进程级 FATAL（exit 127）**而非异常，
    故必须在调用前用文件系统校验拦住。
    """
    from picrecall import simple_tokenizer

    simple_tokenizer._reset_cache()
    fake_dll = tmp_path / "simple.dll"
    fake_dll.write_bytes(b"stub")  # 只为通过 find_library 的存在性判定
    monkeypatch.setattr(simple_tokenizer, "find_library", lambda: str(fake_dll))
    monkeypatch.setattr(simple_tokenizer, "find_dict_dir", lambda lib=None: None)

    ok, reason = simple_tokenizer.availability()
    assert ok is False and "词典" in reason
    with pytest.raises(simple_tokenizer.SimpleUnavailable):
        segment("账单", config.PROFILE_SIMPLE)


def test_simple_availability_probe_never_aborts(monkeypatch):
    """探活是纯文件系统检查：即便 DLL/词典都没有，也必须正常返回 False 而不是中止。"""
    from picrecall import simple_tokenizer

    simple_tokenizer._reset_cache()
    monkeypatch.setattr(simple_tokenizer, "find_library", lambda: None)
    ok, reason = simple_tokenizer.availability()
    assert ok is False and isinstance(reason, str) and reason


@pytest.mark.skipif(
    not __import__("picrecall.simple_tokenizer", fromlist=["x"]).availability()[0],
    reason="libsimple DLL + cppjieba 词典未就位（主路径未启用，属预期）",
)
def test_simple_segment_is_word_level_when_available():
    """主路径真调用（不是只测定义）：词级切分 + 与 char 路径同构 + 确定性。"""
    from picrecall import simple_tokenizer

    toks = simple_tokenizer.simple_tokens("本月账单已生成")
    assert toks == ["本月", "账单", "已", "生成"]
    # 与 char 路径同构：都是"空格连接的 token 串"，可被同一 FTS5 表消费
    assert segment("本月账单已生成", config.PROFILE_SIMPLE).split() == toks
    # 确定性
    assert simple_tokenizer.simple_segment("本月账单已生成") == \
        simple_tokenizer.simple_segment("本月账单已生成")


@pytest.mark.skipif(
    not __import__("picrecall.simple_tokenizer", fromlist=["x"]).availability()[0],
    reason="libsimple DLL + cppjieba 词典未就位（主路径未启用，属预期）",
)
def test_simple_segment_is_lossless_over_cjk():
    """词级切分不得吞字：拼接 token 必须等于原 CJK 串（否则真值失真）。"""
    from picrecall import simple_tokenizer

    for run in ("本月账单已生成", "余额不足请及时充值", "订单号", "设置"):
        joined = "".join(simple_tokenizer.simple_tokens(run))
        assert joined == run, "CJK 往返失真: %r -> %r" % (run, joined)


def test_char_segment_is_deterministic():
    a = segment("本月账单已生成 config error", config.PROFILE_CHAR)
    b = segment("本月账单已生成 config error", config.PROFILE_CHAR)
    assert a == b
