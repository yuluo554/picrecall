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


def test_simple_profile_unavailable_is_explicit():
    """主路径不可用必须显式报错，不静默回落（不冒充可用）。"""
    from picrecall import simple_tokenizer

    with pytest.raises(simple_tokenizer.SimpleUnavailable):
        segment("账单", config.PROFILE_SIMPLE)


def test_char_segment_is_deterministic():
    a = segment("本月账单已生成 config error", config.PROFILE_CHAR)
    b = segment("本月账单已生成 config error", config.PROFILE_CHAR)
    assert a == b
