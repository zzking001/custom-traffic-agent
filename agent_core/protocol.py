"""
控制帧与数据头编解码 — 符合文档第 4 节、第 9 节

帧结构 (第 4.1 节):
  字节偏移     长度    字段
  0            1       command   (0x20)
  1            1       version   (0x01)
  2            1       action
  3            1       flags/status
  4~7          4       task_id
  8~9          2       payload_len
  10~9+N       N       payload
  10+N~13+N    4       crc32
  14+N         1       end (0x10)

数据头 (第 9 节):
  40 字节固定头
"""

import struct
from agent_core.crc import crc32, crc32_bytes, verify_crc

# ── 常量 ──────────────────────────────────────────────
CMD_TRAFFIC = 0x20
PROTO_VERSION = 0x01
FRAME_END = 0x10
COMPAT_PREAMBLE = 0xAA

HEADER_SIZE = 10        # command + version + action + flags + task_id + payload_len
CRC_SIZE = 4
END_SIZE = 1
MIN_FRAME_SIZE = HEADER_SIZE + CRC_SIZE + END_SIZE   # 15 字节
MAX_PAYLOAD_SIZE = 49152

# 数据头
DATA_MAGIC = b"CTFG"
DATA_VERSION = 0x01
DATA_HEADER_LEN = 40

# ── 控制帧打包 ────────────────────────────────────────

def pack_frame(action: int, flags: int, task_id: int,
               payload: bytes = b"") -> bytes:
    """
    打包控制帧。payload 应为 UTF-8 JSON 字节。
    返回完整帧 bytes，不含可选 0xAA。
    """
    payload_len = len(payload)
    if payload_len > MAX_PAYLOAD_SIZE:
        raise ValueError(f"payload 超过 {MAX_PAYLOAD_SIZE} 字节")

    header = struct.pack(
        "!BBBB I H",
        CMD_TRAFFIC,    # command
        PROTO_VERSION,  # version
        action,         # action
        flags,          # flags/status
        task_id,        # 4 字节大端
        payload_len,    # 2 字节大端
    )

    body = header + payload
    crc = crc32_bytes(body)
    return body + crc + bytes([FRAME_END])

def pack_frame_with_preamble(action: int, flags: int, task_id: int,
                             payload: bytes = b"") -> bytes:
    """打包控制帧，前加可选 0xAA 兼容包头"""
    return bytes([COMPAT_PREAMBLE]) + pack_frame(action, flags, task_id, payload)

# ── 控制帧解包 ────────────────────────────────────────

class FrameError(Exception):
    """帧解析错误"""
    pass

def unpack_frame(data: bytes) -> dict:
    """
    解包控制帧，返回 dict。
    自动处理可选 0xAA 前导字节。

    返回:
        {
            "command": int,
            "version": int,
            "action": int,
            "status": int,      # 即 flags 字段，应答时为状态码
            "task_id": int,
            "payload": bytes,   # UTF-8 JSON 字节
            "crc_valid": bool,
        }

    异常:
        FrameError: 帧格式错误
    """
    # 去除可选 0xAA
    if data and data[0] == COMPAT_PREAMBLE:
        data = data[1:]

    if len(data) < MIN_FRAME_SIZE:
        raise FrameError(f"帧太短: {len(data)} < {MIN_FRAME_SIZE}")

    # 结束标识
    if data[-1] != FRAME_END:
        raise FrameError(f"结束标识错误: 期望 0x10, 实际 0x{data[-1]:02x}")

    # 解析固定头: 10 字节
    header = data[:10]
    command, version, action, flags, task_id, payload_len = struct.unpack(
        "!BBBB I H", header
    )

    # 校验
    if command != CMD_TRAFFIC:
        raise FrameError(f"命令号错误: 期望 0x{CMD_TRAFFIC:02x}, 实际 0x{command:02x}")
    if version != PROTO_VERSION:
        raise FrameError(f"版本错误: 期望 0x{PROTO_VERSION:02x}, 实际 0x{version:02x}")
    if payload_len > MAX_PAYLOAD_SIZE:
        raise FrameError(f"payload_len 超限: {payload_len}")

    # 提取 payload
    payload = data[10:10 + payload_len]

    # 期望的总长度
    expected_len = HEADER_SIZE + payload_len + CRC_SIZE + END_SIZE
    if len(data) < expected_len:
        raise FrameError(f"帧长度不足: {len(data)} < {expected_len}")

    # CRC32 校验
    body = data[:HEADER_SIZE + payload_len]         # 从 command 到 payload 尾
    crc_bytes = data[HEADER_SIZE + payload_len:HEADER_SIZE + payload_len + CRC_SIZE]
    expected_crc = int.from_bytes(crc_bytes, 'big')
    crc_valid = verify_crc(body, expected_crc)

    return {
        "command": command,
        "version": version,
        "action": action,
        "status": flags,
        "task_id": task_id,
        "payload": payload,
        "crc_valid": crc_valid,
    }
    # ── 数据头打包/解包 (第 9 节) ─────────────────────────

def pack_data_header(
    task_id: int,
    flow_id: int,
    sequence: int,
    send_timestamp_ns: int = 0,
    payload_len: int = 0,
    pcp: int = 0,
    business_code: int = 0xFF,
    enable_timestamp: bool = True,
) -> bytes:
    """
    打包 40 字节测试数据头。

    参数:
        task_id:          任务标识
        flow_id:          逻辑流标识
        sequence:         64 位报文序号
        send_timestamp_ns: 发送端 Unix 纳秒时间戳
        payload_len:      测试载荷长度
        pcp:              PCP 值 0~7
        business_code:    业务编码 (0x01管理/0x02控制/0x03应用/0x04多媒体/0xFF自定义)
        enable_timestamp: 是否携带有效时间戳 (影响 flags bit0)
    """
    flags = 0x0001 if enable_timestamp else 0x0000

    # 前 36 字节（不含 4 字节 CRC）
    header = struct.pack(
        "!4s B B H I H B B Q Q H H",
        DATA_MAGIC,         # 4B: "CTFG"
        DATA_VERSION,       # 1B: version
        DATA_HEADER_LEN,    # 1B: header_len = 40
        flags,              # 2B: flags
        task_id,            # 4B: task_id
        flow_id,            # 2B: flow_id
        business_code,      # 1B: business_code
        pcp,                # 1B: pcp
        sequence,           # 8B: sequence
        send_timestamp_ns,  # 8B: send_timestamp_ns
        payload_len,        # 2B: payload_len
        0,                  # 2B: reserved
    )

    # CRC32: 对前 36 字节 + 载荷计算
    crc = crc32_bytes(header)  # 此时还没载荷，只校验头
    return header + crc

def unpack_data_header(data: bytes) -> dict:
    """
    解包 40 字节测试数据头。

    返回:
        {
            "magic": bytes,
            "version": int,
            "header_len": int,
            "has_timestamp": bool,
            "task_id": int,
            "flow_id": int,
            "business_code": int,
            "pcp": int,
            "sequence": int,
            "send_timestamp_ns": int,
            "payload_len": int,
            "crc_valid": bool,
        }

    异常:
        FrameError: magic 不匹配或长度不足
    """
    if len(data) < DATA_HEADER_LEN:
        raise FrameError(f"数据头太短: {len(data)} < {DATA_HEADER_LEN}")

    magic, version, header_len, flags, task_id, flow_id, business_code, pcp, \
        sequence, send_timestamp_ns, payload_len, reserved, crc_received = \
        struct.unpack("!4s B B H I H B B Q Q H H 4s", data[:DATA_HEADER_LEN])

    if magic != DATA_MAGIC:
        raise FrameError(f"magic 不匹配: 期望 b'CTFG', 实际 {magic}")

    has_timestamp = bool(flags & 0x0001)

    # CRC32: 对前 36 字节校验
    header_data = data[:36]
    expected_crc = int.from_bytes(crc_received, 'big')
    crc_valid = verify_crc(header_data, expected_crc)

    return {
        "magic": magic,
        "version": version,
        "header_len": header_len,
        "has_timestamp": has_timestamp,
        "task_id": task_id,
        "flow_id": flow_id,
        "business_code": business_code,
        "pcp": pcp,
        "sequence": sequence,
        "send_timestamp_ns": send_timestamp_ns,
        "payload_len": payload_len,
        "crc_valid": crc_valid,
    }