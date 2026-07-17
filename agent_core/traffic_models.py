"""
流量模型 — 符合文档第 6 节

六种模型，统一接口：
  calc_rate(model_config, elapsed_s, packet_size, random_gen) -> float (Mbps)
"""

import math
import random
from typing import Any

def calc_rate(model_config: Any, elapsed_s: float = 0,
              packet_size: int = 1500, rng: random.Random = None) -> float:
    """
    根据模型配置和已运行时间，计算当前瞬时速率 (Mbps)。

    参数:
        model_config: 模型 dict 或字符串 (如 "cbr" 或 {"type":"cbr"})
        elapsed_s:    任务已运行时间 (秒)
        packet_size:  报文大小 (字节)，cbr/poisson 用于计算间隔
        rng:          随机数生成器 (可重现)

    返回:
        瞬时速率 (Mbps)
    """
    if rng is None:
        rng = random.Random()

    # 字符串简写
    if isinstance(model_config, str):
        model_config = {"type": model_config}

    model_type = model_config.get("type", "cbr")

    if model_type == "cbr":
        return _calc_cbr(model_config)
    elif model_type == "poisson":
        return _calc_poisson(model_config)
    elif model_type == "markov":
        return _calc_markov(model_config, elapsed_s, rng)
    elif model_type == "regression":
        return _calc_regression(model_config, elapsed_s)
    elif model_type == "burst":
        return _calc_burst(model_config, elapsed_s)
    elif model_type == "step":
        return _calc_step(model_config, elapsed_s)
    else:
        raise ValueError(f"未知模型类型: {model_type}")

def calc_interval(model_config: Any, packet_size: int,
                  elapsed_s: float = 0, rng: random.Random = None) -> float:
    """
    计算发包间隔 (秒)。

    参数同上，返回两次发包之间的等待时间。
    """
    rate_mbps = calc_rate(model_config, elapsed_s, packet_size, rng)
    if rate_mbps <= 0:
        raise ValueError(f"速率必须 > 0: {rate_mbps}")
    # bits per second → interval
    bits_per_packet = packet_size * 8
    return bits_per_packet / (rate_mbps * 1_000_000)

# ── CBR: 恒定速率 ─────────────────────────────────────

def _calc_cbr(config: dict) -> float:
    return float(config.get("rate_mbps", 0))

# ── Poisson: 指数分布间隔 ─────────────────────────────

def _calc_poisson(config: dict) -> float:
    return float(config.get("rate_mbps", 0))

# ── Markov: 状态转移 ──────────────────────────────────

def _calc_markov(config: dict, elapsed_s: float, rng: random.Random) -> float:
    """
    按状态转移矩阵切换速率状态。
    首次调用时初始化状态，之后按 state_interval_ms 周期转移。

    配置示例:
      {
        "type": "markov",
        "states": [
          {"name": "low",  "rate_mbps": 10},
          {"name": "mid",  "rate_mbps": 50},
          {"name": "high", "rate_mbps": 100}
        ],
        "transition_matrix": [
          [0.7, 0.2, 0.1],
          [0.2, 0.6, 0.2],
          [0.1, 0.3, 0.6]
        ],
        "initial_state": 0,
        "state_interval_ms": 1000
      }
    """
    # 使用 config 对象自身缓存状态（只在首次调用时初始化）
    if "_markov_state" not in config:
        config["_markov_state"] = config.get("initial_state", 0)
        config["_markov_last_switch"] = 0.0

    states = config.get("states", [])
    transition = config.get("transition_matrix", [])
    interval_s = config.get("state_interval_ms", 1000) / 1000.0

    # 检查是否需要切换状态
    if elapsed_s - config["_markov_last_switch"] >= interval_s:
        current = config["_markov_state"]
        # 按转移概率选择下一状态
        probs = transition[current] if current < len(transition) else [1.0]
        config["_markov_state"] = _weighted_choice(probs, rng)
        config["_markov_last_switch"] = elapsed_s

    state_idx = config["_markov_state"]
    if state_idx < len(states):
        return float(states[state_idx].get("rate_mbps", 0))
    return 0.0

def _weighted_choice(weights: list, rng: random.Random) -> int:
    """按权重随机选择索引"""
    total = sum(weights)
    r = rng.random() * total
    cumulative = 0
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            return i
    return len(weights) - 1

# ── Regression: 线性回归 + 时间趋势 + 周期 ─────────────

def _calc_regression(config: dict, elapsed_s: float) -> float:
    """
    线性项 + 时间趋势 + 正弦周期，计算后限幅。

    配置示例:
      {
        "type": "regression",
        "intercept": 100,
        "coefficients": [10, 5],
        "time_coefficient": 2,
        "sine": {"amplitude": 20, "period_s": 60, "phase": 0},
        "min": 0,
        "max": 1000
      }
    """
    intercept = config.get("intercept", 0)
    coefficients = config.get("coefficients", [])
    time_coef = config.get("time_coefficient", 0)
    sine_cfg = config.get("sine", {})
    min_rate = config.get("min", 0)
    max_rate = config.get("max", float("inf"))

    # 线性项：intercept + sum(coefficients)
    linear = intercept + sum(coefficients)

    # 时间趋势
    trend = time_coef * elapsed_s

    # 正弦周期
    periodic = 0.0
    if sine_cfg:
        amp = sine_cfg.get("amplitude", 0)
        period = sine_cfg.get("period_s", 60)
        phase = sine_cfg.get("phase", 0)
        periodic = amp * math.sin(2 * math.pi * elapsed_s / period + phase)

    rate = linear + trend + periodic
    return max(min_rate, min(max_rate, rate))

# ── Burst: 周期突发 ───────────────────────────────────

def _calc_burst(config: dict, elapsed_s: float) -> float:
    """
    在每个周期的突发窗口使用峰值速率，其余时间使用基线速率。

    配置示例:
      {
        "type": "burst",
        "baseline_rate": 100,
        "burst_rate": 1000,
        "burst_duration_ms": 100,
        "period_ms": 1000
      }
    """
    baseline = config.get("baseline_rate", 0)
    burst_rate = config.get("burst_rate", baseline)
    burst_dur = config.get("burst_duration_ms", 0) / 1000.0
    period = config.get("period_ms", 1000) / 1000.0

    if period <= 0:
        return baseline

    phase = elapsed_s % period
    if phase < burst_dur:
        return float(burst_rate)
    return float(baseline)

# ── Step: 阶梯速率 ────────────────────────────────────

def _calc_step(config: dict, elapsed_s: float) -> float:
    """
    在指定时间偏移切换目标速率。

    配置示例:
      {
        "type": "step",
        "stages": [
          {"offset_s": 0,   "rate_mbps": 100},
          {"offset_s": 10,  "rate_mbps": 500},
          {"offset_s": 20,  "rate_mbps": 1000}
        ]
      }
    """
    stages = config.get("stages", [])
    if not stages:
        return 0.0

    # stages 按 offset_s 排序，找最后一个 offset_s <= elapsed_s 的阶段
    current = stages[0]
    for stage in stages:
        if stage.get("offset_s", 0) <= elapsed_s:
            current = stage
        else:
            break
    return float(current.get("rate_mbps", 0))