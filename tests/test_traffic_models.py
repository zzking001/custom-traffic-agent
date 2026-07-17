"""流量模型测试 — 文档第 6 节"""

import math
import random
import pytest
from agent_core.traffic_models import calc_rate, calc_interval

def test_cbr():
    assert calc_rate({"type": "cbr", "rate_mbps": 100}) == 100
    assert calc_rate("cbr") == 0  # 默认 rate_mbps=0

def test_cbr_interval():
    """CBR 100 Mbps, packet 1500 bytes → 固定间隔"""
    # 1500 * 8 = 12000 bits, 100 Mbps → 12000/100e6 = 0.00012s = 120μs
    interval = calc_interval({"type": "cbr", "rate_mbps": 100}, packet_size=1500)
    assert interval == pytest.approx(0.00012, rel=0.01)

def test_poisson():
    """poisson 返回配置速率，随机性由调用方处理间隔"""
    assert calc_rate({"type": "poisson", "rate_mbps": 50}) == 50

def test_burst_baseline():
    """Burst 基线阶段"""
    config = {
        "type": "burst",
        "baseline_rate": 100,
        "burst_rate": 1000,
        "burst_duration_ms": 100,
        "period_ms": 1000,
    }
    # 在 0.5s 时（突发窗口外）
    assert calc_rate(config, elapsed_s=0.5) == 100

def test_burst_peak():
    """Burst 突发窗口内"""
    config = {
        "type": "burst",
        "baseline_rate": 100,
        "burst_rate": 1000,
        "burst_duration_ms": 100,
        "period_ms": 1000,
    }
    # 在 0.05s 时（突发窗口内）
    assert calc_rate(config, elapsed_s=0.05) == 1000

def test_burst_second_period():
    """第二个周期的突发"""
    config = {
        "type": "burst",
        "baseline_rate": 100,
        "burst_rate": 1000,
        "burst_duration_ms": 100,
        "period_ms": 1000,
    }
    assert calc_rate(config, elapsed_s=1.05) == 1000
    assert calc_rate(config, elapsed_s=1.5) == 100

def test_step():
    config = {
        "type": "step",
        "stages": [
            {"offset_s": 0, "rate_mbps": 100},
            {"offset_s": 10, "rate_mbps": 500},
            {"offset_s": 20, "rate_mbps": 1000},
        ]
    }
    assert calc_rate(config, elapsed_s=0) == 100
    assert calc_rate(config, elapsed_s=9) == 100
    assert calc_rate(config, elapsed_s=10) == 500
    assert calc_rate(config, elapsed_s=15) == 500
    assert calc_rate(config, elapsed_s=20) == 1000
    assert calc_rate(config, elapsed_s=999) == 1000

def test_step_empty():
    assert calc_rate({"type": "step", "stages": []}) == 0

def test_regression_basic():
    """回归模型：纯线性项"""
    config = {
        "type": "regression",
        "intercept": 100,
        "coefficients": [10, 20],
        "min": 0,
        "max": 1000,
    }
    # intercept + sum(coeff) = 130
    rate = calc_rate(config, elapsed_s=0)
    assert rate == 130

def test_regression_trend():
    """时间趋势"""
    config = {
        "type": "regression",
        "intercept": 100,
        "time_coefficient": 5,
        "min": 0,
        "max": 1000,
    }
    # at t=0: 100
    assert calc_rate(config, elapsed_s=0) == 100
    # at t=10: 100 + 5*10 = 150
    assert calc_rate(config, elapsed_s=10) == 150

def test_regression_sine():
    """正弦周期"""
    config = {
        "type": "regression",
        "intercept": 100,
        "sine": {"amplitude": 50, "period_s": 10, "phase": 0},
        "min": 0,
        "max": 1000,
    }
    # t=0: 100 + 50*sin(0) = 100
    assert calc_rate(config, elapsed_s=0) == 100
    # t=2.5 (1/4 周期): 100 + 50*sin(π/2) = 150
    assert calc_rate(config, elapsed_s=2.5) == pytest.approx(150)

def test_regression_clamp():
    """限幅"""
    config = {
        "type": "regression",
        "intercept": 100,
        "time_coefficient": -20,
        "min": 10,
        "max": 120,
    }
    # t=0: 100, OK
    assert calc_rate(config, elapsed_s=0) == 100
    # t=10: 100 - 200 = -100 → clamped to 10
    assert calc_rate(config, elapsed_s=10) == 10

def test_markov_initial_state():
    """Markov 初始状态"""
    config = {
        "type": "markov",
        "states": [
            {"name": "low", "rate_mbps": 10},
            {"name": "high", "rate_mbps": 100},
        ],
        "transition_matrix": [[1, 0], [0, 1]],
        "initial_state": 0,
        "state_interval_ms": 100,
    }
    rng = random.Random(42)
    assert calc_rate(config, elapsed_s=0, rng=rng) == 10

def test_markov_transition():
    """一直切换到 state 1"""
    config = {
        "type": "markov",
        "states": [
            {"name": "low", "rate_mbps": 10},
            {"name": "high", "rate_mbps": 100},
        ],
        "transition_matrix": [[0, 1], [0, 1]],  # 必定切到 high
        "initial_state": 0,
        "state_interval_ms": 100,
    }
    rng = random.Random(42)
    # t=0: low
    assert calc_rate(config, elapsed_s=0, rng=rng) == 10
    # t=0.1: >= interval → 切到 high
    assert calc_rate(config, elapsed_s=0.1, rng=rng) == 100

def test_calc_interval_zero_rate():
    with pytest.raises(ValueError):
        calc_interval({"type": "cbr", "rate_mbps": 0}, packet_size=1500)