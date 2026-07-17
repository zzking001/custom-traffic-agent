"""测试载荷生成"""

import pytest
from agent_core.payload import generate_payload

def test_zero():
    payload = generate_payload(10, "zero")
    assert payload == b"\x00" * 10
    assert len(payload) == 10

def test_zero_empty():
    assert generate_payload(0, "zero") == b""

def test_counter():
    payload = generate_payload(12, "counter")
    assert len(payload) == 12
    # 前 4 字节是 0, 中间 4 字节是 1, 后 4 字节是 2
    assert payload[0:4] == (0).to_bytes(4, 'big')
    assert payload[4:8] == (1).to_bytes(4, 'big')
    assert payload[8:12] == (2).to_bytes(4, 'big')

def test_counter_short():
    """长度不是 4 的整数倍"""
    payload = generate_payload(5, "counter")
    assert len(payload) == 5
    # 前 4 字节是 0, 第 5 字节是 1 的第 1 字节 (0x00)
    assert payload[0:4] == (0).to_bytes(4, 'big')
    assert payload[4] == 0x00

def test_random():
    payload = generate_payload(32, "random")
    assert len(payload) == 32
    # 两次生成应不同（概率极高）
    payload2 = generate_payload(32, "random")
    assert payload != payload2

def test_hex():
    payload = generate_payload(6, "hex:aabb")
    assert payload == b"\xaa\xbb" * 3

def test_hex_not_full_repeat():
    """hex 模板不能整除 length"""
    payload = generate_payload(5, "hex:aabb")
    assert len(payload) == 5
    assert payload == b"\xaa\xbb\xaa\xbb\xaa"

def test_hex_empty():
    with pytest.raises(ValueError, match="hex 模板为空"):
        generate_payload(10, "hex:")

def test_hex_invalid():
    with pytest.raises(ValueError, match="无效的十六进制串"):
        generate_payload(10, "hex:xyz")

def test_invalid_pattern():
    with pytest.raises(ValueError, match="不支持的 payload_pattern"):
        generate_payload(10, "nonexistent")

def test_range_check():
    with pytest.raises(ValueError):
        generate_payload(9999, "zero")