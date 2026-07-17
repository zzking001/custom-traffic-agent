"""统计计算测试 — 文档第 8 节、第 10 节"""

import pytest
from agent_core.statistics import (
    compute_latency_stats,
    compute_jitter,
    SequenceTracker,
)

# ── 时延统计 ──────────────────────────────────────────

def test_latency_empty():
    stats = compute_latency_stats([])
    assert stats["count"] == 0
    assert stats["avg_us"] == 0

def test_latency_single():
    stats = compute_latency_stats([100.0])
    assert stats["count"] == 1
    assert stats["avg_us"] == 100.0
    assert stats["min_us"] == 100.0
    assert stats["max_us"] == 100.0

def test_latency_basic():
    samples = [10.0, 20.0, 30.0, 40.0, 50.0]
    stats = compute_latency_stats(samples)
    assert stats["count"] == 5
    assert stats["avg_us"] == 30.0
    assert stats["min_us"] == 10.0
    assert stats["max_us"] == 50.0

def test_latency_percentiles():
    """P95/P99 计算"""
    # 100 个样本: 1, 2, 3, ..., 100
    samples = list(range(1, 101))
    stats = compute_latency_stats(samples)
    # P95: 第 95 百分位，排名 = 0.95 * 99 = 94.05
    # 线性插值: data[94]=95, data[95]=96 → 95 + 0.05 = 95.05
    assert stats["p95_us"] == pytest.approx(95.05)
    # P99: 排名 = 0.99 * 99 = 98.01 → data[98]=99, data[99]=100
    assert stats["p99_us"] == pytest.approx(99.01)

# ── 抖动 ─────────────────────────────────────────────

def test_jitter_empty():
    j = compute_jitter([])
    assert j["avg_us"] == 0
    assert j["max_us"] == 0

def test_jitter_single():
    j = compute_jitter([100.0])
    assert j["avg_us"] == 0

def test_jitter_calculation():
    # 差值: |20-10|=10, |35-20|=15, |25-35|=10
    samples = [10.0, 20.0, 35.0, 25.0]
    j = compute_jitter(samples)
    assert j["avg_us"] == pytest.approx((10 + 15 + 10) / 3)
    assert j["max_us"] == 15.0

# ── 序号追踪 ──────────────────────────────────────────

def test_sequence_normal():
    tracker = SequenceTracker()
    for i in range(100):
        tracker.feed(i)
    stats = tracker.estimate_loss()
    assert stats["lost_packets"] == 0
    assert stats["loss_pct"] == 0.0
    assert stats["duplicate_packets"] == 0
    assert stats["out_of_order_packets"] == 0

def test_sequence_lost():
    """丢掉 seq 3, 5, 6"""
    tracker = SequenceTracker()
    tracker.feed(0)
    tracker.feed(1)
    tracker.feed(2)
    tracker.feed(4)
    tracker.feed(7)
    stats = tracker.estimate_loss()
    # expected = 7+1 = 8
    # lost: seq_max 从 2→4 丢 3 (1个), 从 4→7 丢 5,6 (2个) = 3
    assert stats["expected_packets"] == 8
    assert stats["lost_packets"] == 3
    assert stats["loss_pct"] == pytest.approx(37.5)

def test_sequence_duplicate():
    tracker = SequenceTracker()
    tracker.feed(0)
    tracker.feed(1)
    tracker.feed(1)  # 重复
    tracker.feed(2)
    stats = tracker.estimate_loss()
    assert stats["duplicate_packets"] == 1
    assert stats["lost_packets"] == 0

def test_sequence_out_of_order():
    tracker = SequenceTracker()
    tracker.feed(0)
    tracker.feed(2)
    tracker.feed(1)  # 乱序
    tracker.feed(3)
    stats = tracker.estimate_loss()
    assert stats["out_of_order_packets"] == 1
    # seq_max 更新逻辑：0→2(丢1), 2→1(不更新seq_max,但已被收到), 1→3(丢? seq_max已是2, 3-2-1=0)
    # expected = 3+1 = 4, lost = 1 (seq 1 虽然乱序但收到了)
    assert stats["expected_packets"] == 4

def test_sequence_empty():
    tracker = SequenceTracker()
    stats = tracker.estimate_loss()
    assert stats["expected_packets"] == 0