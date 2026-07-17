"""任务配置校验测试 — 文档第 5 节"""

import pytest
from agent_core.config_validator import (
    validate_task_config,
    calculate_target_rates,
)

def make_minimal_config(**overrides):
    """构造最小合法配置"""
    config = {
        "duration_s": 10,
        "flows": [
            {
                "flow_id": 1,
                "role": "sender",
                "destination_ip": "192.168.0.2",
                "destination_port": 61001,
                "target_rate_mbps": 100,
            }
        ]
    }
    config.update(overrides)
    return config

# ── 顶层字段 ──────────────────────────────────────────

def test_valid_minimal():
    ok, err = validate_task_config(make_minimal_config())
    assert ok, err

def test_missing_duration():
    config = {"flows": []}
    ok, err = validate_task_config(config)
    assert not ok
    assert "duration_s" in err

def test_duration_range():
    ok, _ = validate_task_config(make_minimal_config(duration_s=0.05))
    assert not ok

    ok, _ = validate_task_config(make_minimal_config(duration_s=90000))
    assert not ok

def test_task_name_too_long():
    ok, _ = validate_task_config(make_minimal_config(task_name="x" * 129))
    assert not ok

def test_start_delay_range():
    ok, _ = validate_task_config(make_minimal_config(start_delay_ms=-1))
    assert not ok
    ok, _ = validate_task_config(make_minimal_config(start_delay_ms=999999))
    assert not ok

# ── flows 数组 ────────────────────────────────────────

def test_flows_empty():
    config = make_minimal_config(flows=[])
    ok, _ = validate_task_config(config)
    assert not ok

def test_flows_too_many():
    config = make_minimal_config(flows=[{
        "flow_id": i, "role": "sender",
        "destination_ip": "192.168.0.2",
        "destination_port": 61001,
        "target_rate_mbps": 1,
    } for i in range(1, 34)])
    ok, _ = validate_task_config(config)
    assert not ok

def test_flow_id_range():
    ok, _ = validate_task_config(make_minimal_config(flows=[{
        "flow_id": 0, "role": "sender",
        "destination_ip": "192.168.0.2",
        "destination_port": 61001,
        "target_rate_mbps": 100,
    }]))
    assert not ok

def test_role_invalid():
    ok, _ = validate_task_config(make_minimal_config(flows=[{
        "flow_id": 1, "role": "invalid",
        "destination_ip": "192.168.0.2",
        "destination_port": 61001,
        "target_rate_mbps": 100,
    }]))
    assert not ok

# ── receiver 必填 ────────────────────────────────────

def test_receiver_missing_port():
    config = make_minimal_config(flows=[{
        "flow_id": 1, "role": "receiver",
    }])
    ok, err = validate_task_config(config)
    assert not ok
    assert "local_port" in err

def test_receiver_valid():
    config = make_minimal_config(flows=[{
        "flow_id": 1, "role": "receiver",
        "local_port": 61001,
    }])
    ok, _ = validate_task_config(config)
    assert ok

# ── sender 必填 ──────────────────────────────────────

def test_sender_missing_destination():
    config = make_minimal_config(flows=[{
        "flow_id": 1, "role": "sender",
        "target_rate_mbps": 100,
    }])
    ok, err = validate_task_config(config)
    assert not ok
    assert "destination" in err

# ── 业务占比 ──────────────────────────────────────────

def test_rate_percent_sum_not_100():
    config = {
        "duration_s": 10,
        "total_rate_mbps": 1000,
        "flows": [
            {"flow_id": 1, "role": "sender", "destination_ip": "192.168.0.2",
             "destination_port": 61001, "rate_percent": 30},
            {"flow_id": 2, "role": "sender", "destination_ip": "192.168.0.3",
             "destination_port": 61002, "rate_percent": 30},
        ]
    }
    ok, _ = validate_task_config(config)
    assert not ok

def test_rate_percent_sum_100():
    config = {
        "duration_s": 10,
        "total_rate_mbps": 1000,
        "flows": [
            {"flow_id": 1, "role": "sender", "destination_ip": "192.168.0.2",
             "destination_port": 61001, "rate_percent": 40},
            {"flow_id": 2, "role": "sender", "destination_ip": "192.168.0.3",
             "destination_port": 61002, "rate_percent": 60},
        ]
    }
    ok, _ = validate_task_config(config)
    assert ok

def test_rate_percent_missing_total_rate():
    config = {
        "duration_s": 10,
        "flows": [
            {"flow_id": 1, "role": "sender", "destination_ip": "192.168.0.2",
             "destination_port": 61001, "rate_percent": 100},
        ]
    }
    ok, err = validate_task_config(config)
    assert not ok
    assert "total_rate_mbps" in err

def test_calculate_target_rates():
    flows = [
        {"flow_id": 1, "role": "sender", "rate_percent": 30},
        {"flow_id": 2, "role": "sender", "rate_percent": 70},
        {"flow_id": 3, "role": "receiver", "local_port": 61001},
    ]
    result = calculate_target_rates(flows, 1000)
    assert result[0]["target_rate_mbps"] == 300
    assert result[1]["target_rate_mbps"] == 700
    assert "target_rate_mbps" not in result[2]  # receiver 不受影响

# ── TCP / mode ───────────────────────────────────────

def test_tcp_only_unicast():
    config = make_minimal_config(flows=[{
        "flow_id": 1, "role": "sender",
        "transport": "tcp", "mode": "broadcast",
        "destination_ip": "192.168.0.2",
        "destination_port": 61001,
        "target_rate_mbps": 100,
    }])
    ok, _ = validate_task_config(config)
    assert not ok

# ── 文档第 7 节示例 ──────────────────────────────────

def test_document_example():
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
                "rate_percent": 100,
                "model": {"type": "cbr"}
            }
        ]
    }
    ok, err = validate_task_config(config)
    assert ok, err