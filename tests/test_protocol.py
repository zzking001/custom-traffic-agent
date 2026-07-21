"""
控制帧打包/解包测试
"""

import json
import pytest
from agent_core.protocol import (
    pack_frame,
    pack_frame_with_preamble,
    unpack_frame,
    FrameError,
    CMD_TRAFFIC,
    PROTO_VERSION,
    FRAME_END,
    COMPAT_PREAMBLE,
)

def test_pack_minimal_frame():
    """最小帧：无 payload"""
    # CAPABILITY 命令，action=0x05, flags=0, task_id=0, payload 为空
    frame = pack_frame(action=0x05, flags=0x00, task_id=0)
    # 10 字节头 + 0 payload + 4 CRC + 1 end = 15 字节
    assert len(frame) == 15
    assert frame[0] == CMD_TRAFFIC
    assert frame[1] == PROTO_VERSION
    assert frame[2] == 0x05
    assert frame[3] == 0x00
    assert frame[-1] == FRAME_END

def test_pack_with_payload():
    """带 JSON payload"""
    payload = b'{"task_name":"test"}'
    frame = pack_frame(action=0x01, flags=0x00, task_id=42, payload=payload)
    # 10 + len(payload) + 4 + 1
    assert len(frame) == 10 + len(payload) + 4 + 1
    # 检查 task_id
    import struct
    task_id = struct.unpack("!I", frame[4:8])[0]
    assert task_id == 42
    # 检查 payload_len
    payload_len = struct.unpack("!H", frame[8:10])[0]
    assert payload_len == len(payload)

def test_pack_payload_too_large():
    """payload 超过 49152 字节"""
    with pytest.raises(ValueError):
        pack_frame(action=0x01, flags=0x00, task_id=0, payload=b"x" * 49153)

def test_pack_with_preamble():
    """带 0xAA 前导"""
    frame = pack_frame_with_preamble(action=0x03, flags=0x00, task_id=0)
    assert frame[0] == COMPAT_PREAMBLE
    assert len(frame) == 16  # 1 + 15

def test_unpack_roundtrip():
    """打包后解包，数据一致"""
    payload = b'{"flows":[{"flow_id":1,"role":"sender"}]}'
    original_action = 0x01
    original_flags = 0x00
    original_task_id = 100

    frame = pack_frame(original_action, original_flags, original_task_id, payload)
    result = unpack_frame(frame)

    assert result["action"] == original_action
    assert result["status"] == original_flags
    assert result["task_id"] == original_task_id
    assert result["payload"] == payload
    assert result["crc_valid"] is True

def test_unpack_with_preamble():
    """带 0xAA 前导的帧也能正常解包"""
    frame = pack_frame_with_preamble(action=0x81, flags=0x00, task_id=200)
    result = unpack_frame(frame)
    assert result["action"] == 0x81
    assert result["task_id"] == 200
    assert result["crc_valid"] is True

def test_unpack_crc_invalid():
    """CRC 错误"""
    frame = pack_frame(action=0x01, flags=0x00, task_id=1)
    # 篡改 payload 后重算 CRC 的部分 — 直接改数据中间一个字节
    bad = bytearray(frame)
    bad[10] ^= 0xFF  # 翻转 CRC 区域的第一个字节
    result = unpack_frame(bytes(bad))
    assert result["crc_valid"] is False

def test_unpack_bad_command():
    """命令号错误"""
    frame = pack_frame(action=0x01, flags=0x00, task_id=0)
    bad = bytearray(frame)
    bad[0] = 0xFF
    with pytest.raises(FrameError, match="命令号错误"):
        unpack_frame(bytes(bad))

def test_unpack_bad_version():
    """版本错误"""
    frame = pack_frame(action=0x01, flags=0x00, task_id=0)
    bad = bytearray(frame)
    bad[1] = 0xFF
    with pytest.raises(FrameError, match="版本错误"):
        unpack_frame(bytes(bad))

def test_unpack_bad_end():
    """结束标识错误"""
    frame = pack_frame(action=0x01, flags=0x00, task_id=0)
    bad = bytearray(frame)
    bad[-1] = 0xFF
    with pytest.raises(FrameError, match="结束标识错误"):
        unpack_frame(bytes(bad))

def test_unpack_too_short():
    """帧太短"""
    with pytest.raises(FrameError, match="帧太短"):
        unpack_frame(b"\x20\x01")

def test_unpack_realistic_start():
    """模拟文档第 7 节的 START 示例"""
    config = {
        "schema_version": "1.0",
        "task_name": "混合业务发送任务",
        "duration_s": 60,
        "total_rate_mbps": 1000,
        "start_delay_ms": 500,
        "result_push_enabled": True,
        "flows": [
            {
                "flow_id": 101,
                "name": "管理数据",
                "role": "sender",
                "business_type": "management",
                "transport": "udp",
                "mode": "unicast",
                "destination_ip": "192.168.0.2",
                "destination_port": 61001,
                "vlan_id": 100,
                "pcp": 7,
                "packet_size_min": 64,
                "packet_size_max": 128,
                "rate_percent": 5,
                "model": {"type": "cbr"}
            }
        ]
    }
    payload = json.dumps(config, ensure_ascii=False).encode("utf-8")

    # 打包
    frame = pack_frame(action=0x01, flags=0x00, task_id=1, payload=payload)

    # 解包
    result = unpack_frame(frame)
    assert result["action"] == 0x01
    assert result["task_id"] == 1
    assert result["crc_valid"] is True

    # 验证 JSON 可解析且内容一致
    parsed = json.loads(result["payload"].decode("utf-8"))
    assert parsed["task_name"] == "混合业务发送任务"
    assert len(parsed["flows"]) == 1
    assert parsed["flows"][0]["flow_id"] == 101
    # ── 数据头测试 ─────────────────────────────────────────

from agent_core.protocol import (
    pack_data_header,
    unpack_data_header,
    DATA_MAGIC,
    DATA_HEADER_LEN,
    BUSINESS_MGMT,
    BUSINESS_APP,
)

def test_pack_data_header():
    """打包数据头"""
    header = pack_data_header(
        task_id=1,
        flow_id=101,
        sequence=0,
        payload_len=100,
        pcp=7,
        business_code=BUSINESS_MGMT,
    )
    assert len(header) == DATA_HEADER_LEN
    assert header[:4] == DATA_MAGIC


def test_unpack_data_header_roundtrip():
    """数据头打包解包往返（无载荷）"""
    original = pack_data_header(
        task_id=42,
        flow_id=201,
        sequence=999,
        send_timestamp_ns=1234567890,
        payload_len=500,
        pcp=4,
        business_code=BUSINESS_APP,
        enable_timestamp=True,
    )
    result = unpack_data_header(original)

    assert result["task_id"] == 42
    assert result["flow_id"] == 201
    assert result["sequence"] == 999
    assert result["send_timestamp_ns"] == 1234567890
    assert result["payload_len"] == 500
    assert result["pcp"] == 4
    assert result["business_code"] == BUSINESS_APP
    assert result["has_timestamp"] is True
    assert result["crc_valid"] is True


def test_data_header_with_payload_crc():
    """[2025-07-17 新增] CRC 覆盖头+载荷，往返验证"""
    payload_data = b"\x01\x02\x03\x04\x05"
    header = pack_data_header(
        task_id=42,
        flow_id=1,
        sequence=0,
        payload_len=len(payload_data),
        payload=payload_data,  # 传入载荷参与 CRC
    )
    # 拼成完整报文：40 字节头 + 载荷
    full_packet = header + payload_data
    result = unpack_data_header(full_packet)
    assert result["crc_valid"] is True


def test_data_header_payload_crc_tamper():
    """[2025-07-17 新增] 篡改载荷后 CRC 失效"""
    payload_data = b"\x01\x02\x03\x04\x05"
    header = pack_data_header(
        task_id=1,
        flow_id=1,
        sequence=0,
        payload_len=len(payload_data),
        payload=payload_data,
    )
    full_packet = bytearray(header + payload_data)
    full_packet[41] ^= 0xFF  # 篡改载荷第一个字节
    result = unpack_data_header(bytes(full_packet))
    assert result["crc_valid"] is False

def test_data_header_no_timestamp():
    """不启用时延统计"""
    header = pack_data_header(
        task_id=1,
        flow_id=1,
        sequence=0,
        enable_timestamp=False,
    )
    result = unpack_data_header(header)
    assert result["has_timestamp"] is False
    assert result["crc_valid"] is True

def test_data_header_bad_magic():
    """magic 不匹配"""
    header = pack_data_header(task_id=1, flow_id=1, sequence=0)
    bad = bytearray(header)
    bad[0] = 0xFF
    with pytest.raises(FrameError, match="magic"):
        unpack_data_header(bytes(bad))

def test_data_header_crc_invalid():
    """CRC 错误"""
    header = pack_data_header(task_id=1, flow_id=1, sequence=0)
    bad = bytearray(header)
    bad[36] ^= 0xFF  # CRC 首字节
    result = unpack_data_header(bytes(bad))
    assert result["crc_valid"] is False