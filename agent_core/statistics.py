"""
接收端统计计算 — 符合文档第 8 节、第 10 节

包含:
  时延统计 (avg/min/max/p95/p99) — 最多保留 10000 样本
  抖动计算 (相邻差值)
  丢包估算 (基于序号范围)
  乱序/重复检测
"""

import math
from typing import List, Set

MAX_LATENCY_SAMPLES = 10000

# ── 时延统计 ──────────────────────────────────────────

def compute_latency_stats(samples: List[float]) -> dict:
    """
    计算时延统计指标。

    参数:
        samples: 单向时延样本列表 (单位 μs)

    返回:
        {
            "count": int,
            "avg_us": float,
            "min_us": float,
            "max_us": float,
            "p95_us": float,
            "p99_us": float,
        }
        样本为空时返回全 0。
    """
    if not samples:
        return {
            "count": 0,
            "avg_us": 0.0,
            "min_us": 0.0,
            "max_us": 0.0,
            "p95_us": 0.0,
            "p99_us": 0.0,
        }

    sorted_samples = sorted(samples)
    n = len(sorted_samples)

    return {
        "count": n,
        "avg_us": sum(samples) / n,
        "min_us": sorted_samples[0],
        "max_us": sorted_samples[-1],
        "p95_us": _percentile(sorted_samples, 95),
        "p99_us": _percentile(sorted_samples, 99),
    }

def compute_jitter(samples: List[float]) -> dict:
    """
    计算抖动：相邻有效时延样本差值的绝对值。

    返回:
        {
            "avg_us": float,
            "max_us": float,
        }
        样本不足 2 时返回全 0。
    """
    if len(samples) < 2:
        return {"avg_us": 0.0, "max_us": 0.0}

    diffs = [abs(samples[i] - samples[i - 1]) for i in range(1, len(samples))]
    return {
        "avg_us": sum(diffs) / len(diffs),
        "max_us": max(diffs),
    }

def _percentile(sorted_data: List[float], p: int) -> float:
    """计算百分位数 (线性插值)"""
    n = len(sorted_data)
    if n == 0:
        return 0.0
    rank = (p / 100.0) * (n - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return sorted_data[lo]
    frac = rank - lo
    return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac

# ── 序号追踪 ──────────────────────────────────────────

class SequenceTracker:
    """
    追踪报文序号，检测丢包、重复、乱序。

    用法:
        tracker = SequenceTracker()
        tracker.feed(sequence_number)

        tracker.lost_packets          → int
        tracker.duplicate_packets     → int
        tracker.out_of_order_packets  → int
    """

    def __init__(self):
        self.last_seq: int = -1          # 上一个收到的序号
        self.seq_max: int = -1           # 目前见过的最大序号
        self.received: Set[int] = set()  # 所有收到过的序号

        self.lost_packets = 0
        self.duplicate_packets = 0
        self.out_of_order_packets = 0
        self.total_received = 0

    def feed(self, seq: int):
        """处理一个收到的序号"""
        self.total_received += 1

        # 重复检测
        if seq in self.received:
            self.duplicate_packets += 1
            return

        self.received.add(seq)

        # 乱序检测：比之前最大的小
        if self.seq_max >= 0 and seq < self.seq_max:
            self.out_of_order_packets += 1

        # 更新最大序号
        if seq > self.seq_max:
            # 间隙填充：新 seq 超过旧的 seq_max，中间的序号视为丢失
            if self.seq_max >= 0:
                gap = seq - self.seq_max - 1
                self.lost_packets += gap
            self.seq_max = seq

        self.last_seq = seq

    def estimate_loss(self) -> dict:
        """
        根据序号范围估算丢包。
        返回:
            {
                "expected_packets": int,      # 期望收到的最小包数
                "lost_packets": int,          # 估算丢包数
                "loss_pct": float,            # 丢包率
                "duplicate_packets": int,
                "out_of_order_packets": int,
            }
        """
        if self.seq_max < 0:
            return {
                "expected_packets": 0,
                "lost_packets": 0,
                "loss_pct": 0.0,
                "duplicate_packets": 0,
                "out_of_order_packets": 0,
            }

        expected = self.seq_max + 1  # 序号从 0 开始
        loss = self.lost_packets
        pct = (loss / expected * 100) if expected > 0 else 0.0

        return {
            "expected_packets": expected,
            "lost_packets": loss,
            "loss_pct": round(pct, 4),
            "duplicate_packets": self.duplicate_packets,
            "out_of_order_packets": self.out_of_order_packets,
        }