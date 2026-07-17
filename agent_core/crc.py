"""
CRC32 校验 — 符合文档第 3 节规范
算法: CRC-32/ISO-HDLC
多项式: 0x04C11DB7
输入/输出反射: 是
初始值: 0xFFFFFFFF
结果异或值: 0xFFFFFFFF
"""

import binascii

def crc32(data: bytes) -> int:
    """
    计算 ISO-HDLC CRC32，返回 32 位无符号整数。
    与 Python binascii.crc32 一致，直接使用。
    """
    return binascii.crc32(data) & 0xFFFFFFFF

def crc32_bytes(data: bytes) -> bytes:
    """
    返回 4 字节大端序 CRC32，用于写入帧。
    """
    return crc32(data).to_bytes(4, 'big')

def verify_crc(data: bytes, expected: int) -> bool:
    """
    校验 data 的 CRC32 是否等于 expected。
    用于解包帧时验证。data 不含 CRC 字段本身。
    """
    return crc32(data) == expected