"""
验证 CRC32 实现与文档规范一致
"""

from agent_core.crc import crc32, crc32_bytes, verify_crc

def test_empty():
    """空数据 CRC32 应为 0x00000000（初值异或后）"""
    assert crc32(b"") == 0x00000000

def test_known_vector():
    """
    已知测试向量：字符串 "123456789" 的 ISO-HDLC CRC32
    标准值: 0xCBF43926
    """
    assert crc32(b"123456789") == 0xCBF43926

def test_crc32_bytes():
    """返回 4 字节大端序"""
    assert crc32_bytes(b"123456789") == b"\xcb\xf4\x39\x26"

def test_verify_pass():
    """校验通过"""
    data = b"\x01\x02\x03"
    checksum = crc32(data)
    assert verify_crc(data, checksum) is True

def test_verify_fail():
    """校验失败"""
    data = b"\x01\x02\x03"
    assert verify_crc(data, 0xDEADBEEF) is False

def test_document_example_style():
    """
    模拟文档帧结构：从 command 到 payload 最后 1 字节计算 CRC
    构造一个最小合法帧的 CRC 计算
    """
    # command=0x20, version=0x01, action=0x05 (CAPABILITY),
    # flags=0x00, task_id=0, payload_len=0
    header = bytes([0x20, 0x01, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    c = crc32(header)
    # 结果应为 4 字节
    assert 0 <= c <= 0xFFFFFFFF
    b = crc32_bytes(header)
    assert len(b) == 4