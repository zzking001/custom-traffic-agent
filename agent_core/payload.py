"""
测试载荷生成 — 符合文档第 5.2 节 payload_pattern 字段

支持模式:
  counter    — 4 字节递增计数器重复填充
  zero       — 全零
  random     — 随机字节
  hex:...    — 十六进制串重复填充
"""

import os

def generate_payload(length: int, pattern: str = "zero") -> bytes:
    """
    生成指定长度的测试载荷。

    参数:
        length:  载荷字节数 (0~9176)
        pattern: "counter" / "zero" / "random" / "hex:..."

    返回:
        长度恰好为 length 的 bytes
    """
    if length == 0:
        return b""

    if not (0 <= length <= 9176):
        raise ValueError(f"length 超出范围: {length}")

    if pattern == "zero":
        return b"\x00" * length

    elif pattern == "counter":
        # 4 字节大端递增计数器，循环填充
        counter_size = 4
        repeats = (length + counter_size - 1) // counter_size
        parts = []
        for i in range(repeats):
            parts.append(i.to_bytes(counter_size, 'big'))
        return b"".join(parts)[:length]

    elif pattern == "random":
        return os.urandom(length)

    elif pattern.startswith("hex:"):
        hex_str = pattern[4:]
        try:
            template = bytes.fromhex(hex_str)
        except ValueError:
            raise ValueError(f"无效的十六进制串: {hex_str}")
        if len(template) == 0:
            raise ValueError("hex 模板为空")
        repeats = (length + len(template) - 1) // len(template)
        return (template * repeats)[:length]

    else:
        raise ValueError(f"不支持的 payload_pattern: {pattern}")