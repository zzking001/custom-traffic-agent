"""
START 任务配置校验 — 符合文档第 5 节

校验顶层字段和每条 flow 的类型、范围、必填/条件必填约束。
"""

from typing import Tuple, List, Optional

# ── 常量范围 ──────────────────────────────────────────
VALID_BUSINESS_TYPES = {"management", "control", "application", "multimedia", "custom"}
VALID_TRANSPORTS = {"udp", "tcp"}
VALID_MODES = {"unicast", "multicast", "broadcast"}
VALID_PAYLOAD_PATTERNS = {"counter", "zero", "random"}  # hex:... 按前缀匹配
VALID_MODEL_TYPES = {"cbr", "poisson", "markov", "regression", "burst", "step"}

#   校验 START 命令的任务配置 JSON
def validate_task_config(config: dict) -> Tuple[bool, Optional[str]]:
    if not isinstance(config, dict):
        return False, "配置必须是 JSON 对象"

    # ── 顶层字段 ──────────────────────────────────
    ok, err = _validate_top_level(config)
    if not ok:
        return False, err

    # ── flows 数组 ─────────────────────────────────
    flows = config.get("flows", [])
    if not isinstance(flows, list):
        return False, "flows 必须是数组"
    if len(flows) < 1 or len(flows) > 32:
        return False, f"flows 数量 {len(flows)} 超出范围 [1, 32]"

    for i, flow in enumerate(flows):
        ok, err = _validate_flow(flow, i, config)
        if not ok:
            return False, err

    # ── 业务占比校验 ────────────────────────────────
    ok, err = _validate_rate_percent(flows, config)
    if not ok:
        return False, err

    return True, None

#   上个函数的辅助函数，校验顶层字段
def _validate_top_level(config: dict) -> Tuple[bool, Optional[str]]:

    # duration_s: 必填, 0.1~86400
    duration = config.get("duration_s")
    if duration is None:
        return False, "缺少必填字段: duration_s"
    if not isinstance(duration, (int, float)):
        return False, f"duration_s 必须是数字, 实际: {type(duration).__name__}"
    if not (0.1 <= duration <= 86400):
        return False, f"duration_s={duration} 超出范围 [0.1, 86400]"

    # task_name: 可选, 最长 128 字符
    task_name = config.get("task_name")
    if task_name is not None:
        if not isinstance(task_name, str):
            return False, f"task_name 必须是字符串"
        if len(task_name) > 128:
            return False, f"task_name 超过 128 字符"

    # start_delay_ms: 可选, 0~600000
    delay = config.get("start_delay_ms")
    if delay is not None:
        if not isinstance(delay, int):
            return False, f"start_delay_ms 必须是整数"
        if not (0 <= delay <= 600000):
            return False, f"start_delay_ms={delay} 超出范围 [0, 600000]"

    # report_interval_ms: 可选, 100~60000
    interval = config.get("report_interval_ms")
    if interval is not None:
        if not isinstance(interval, int):
            return False, f"report_interval_ms 必须是整数"
        if not (100 <= interval <= 60000):
            return False, f"report_interval_ms={interval} 超出范围 [100, 60000]"

    # random_seed: 可选, 0~2^32-1
    seed = config.get("random_seed")
    if seed is not None:
        if not isinstance(seed, int):
            return False, f"random_seed 必须是整数"
        if not (0 <= seed < 2**32):
            return False, f"random_seed={seed} 超出范围"

    return True, None

#   上面函数的辅助函数，校验业务流字段
def _validate_flow(flow: dict, idx: int, top_config: dict) -> Tuple[bool, Optional[str]]:
    """校验单条 flow"""
    prefix = f"flows[{idx}]"

    if not isinstance(flow, dict):
        return False, f"{prefix}: 必须是 JSON 对象"

    # flow_id: 必填, 1~65535
    fid = flow.get("flow_id")
    if fid is None:
        return False, f"{prefix}: 缺少必填字段 flow_id"
    if not isinstance(fid, int) or not (1 <= fid <= 65535):
        return False, f"{prefix}: flow_id={fid} 必须为 1~65535 的整数"

    # role: 必填
    role = flow.get("role")
    if role not in ("sender", "receiver"):
        return False, f"{prefix}: role 必须是 sender 或 receiver, 实际: {role}"

    # name: 可选, 最长 128
    name = flow.get("name")
    if name is not None and (not isinstance(name, str) or len(name) > 128):
        return False, f"{prefix}: name 超过 128 字符"

    # business_type
    bt = flow.get("business_type", "custom")
    if bt not in VALID_BUSINESS_TYPES:
        return False, f"{prefix}: 无效的 business_type: {bt}"

    # transport
    transport = flow.get("transport", "udp")
    if transport not in VALID_TRANSPORTS:
        return False, f"{prefix}: 无效的 transport: {transport}"

    # mode
    mode = flow.get("mode", "unicast")
    if mode not in VALID_MODES:
        return False, f"{prefix}: 无效的 mode: {mode}"
    if transport == "tcp" and mode != "unicast":
        return False, f"{prefix}: TCP 仅支持 unicast"

    # pcp
    pcp = flow.get("pcp", 0)
    if not isinstance(pcp, int) or not (0 <= pcp <= 7):
        return False, f"{prefix}: pcp={pcp} 必须为 0~7"

    # dscp
    dscp = flow.get("dscp", 0)
    if not isinstance(dscp, int) or not (0 <= dscp <= 63):
        return False, f"{prefix}: dscp={dscp} 必须为 0~63"

    # ttl
    ttl = flow.get("ttl", 64)
    if not isinstance(ttl, int) or not (1 <= ttl <= 255):
        return False, f"{prefix}: ttl={ttl} 必须为 1~255"

    # packet_size / packet_size_min/max
    if not _validate_packet_size(flow, prefix):
        return False, f"{prefix}: packet_size 校验失败"

    # ── role 相关的条件必填 ──────────────────────────
    if role == "receiver":
        # local_port 必填
        lp = flow.get("local_port")
        if lp is None or not isinstance(lp, int) or not (1 <= lp <= 65535):
            return False, f"{prefix}: receiver 必须指定 local_port (1~65535)"

    if role == "sender":
        # destination_ip 必填
        dip = flow.get("destination_ip")
        if not dip or not isinstance(dip, str):
            return False, f"{prefix}: sender 必须指定 destination_ip"

        # destination_port 必填
        dp = flow.get("destination_port")
        if dp is None or not isinstance(dp, int) or not (1 <= dp <= 65535):
            return False, f"{prefix}: sender 必须指定 destination_port (1~65535)"

        # target_rate_mbps: 条件必填（不配 rate_percent 时必填）
        has_rate_percent = "rate_percent" in flow
        has_target_rate = "target_rate_mbps" in flow
        if not has_rate_percent and not has_target_rate:
            return False, f"{prefix}: sender 必须指定 target_rate_mbps 或 rate_percent"
        if has_target_rate:
            tr = flow["target_rate_mbps"]
            if not isinstance(tr, (int, float)) or tr > 100000:
                return False, f"{prefix}: target_rate_mbps={tr} 必须 ≤ 100000"

    # rate_percent
    rp = flow.get("rate_percent")
    if rp is not None:
        if not isinstance(rp, (int, float)) or not (0 < rp <= 100):
            return False, f"{prefix}: rate_percent={rp} 必须 >0 且 ≤100"

    # payload_pattern
    pp = flow.get("payload_pattern", "zero")
    if isinstance(pp, str):
        if pp not in VALID_PAYLOAD_PATTERNS and not pp.startswith("hex:"):
            return False, f"{prefix}: 无效的 payload_pattern: {pp}"

    # model
    model = flow.get("model", {"type": "cbr"})
    if isinstance(model, str):
        model = {"type": model}
    if isinstance(model, dict):
        mt = model.get("type", "cbr")
        if mt not in VALID_MODEL_TYPES:
            return False, f"{prefix}: 无效的 model.type: {mt}"

    # duration_s (flow 级别)
    fd = flow.get("duration_s")
    if fd is not None:
        task_dur = top_config.get("duration_s", 0)
        if not isinstance(fd, (int, float)) or fd > task_dur:
            return False, f"{prefix}: flow.duration_s={fd} 超过任务总时长 {task_dur}"

    # receive_grace_ms
    rg = flow.get("receive_grace_ms", 500)
    if not isinstance(rg, int) or not (0 <= rg <= 60000):
        return False, f"{prefix}: receive_grace_ms={rg} 必须为 0~60000"

    # boolean 字段
    for field in ["result_push_enabled", "latency_measurement", "sequence_check"]:
        val = flow.get(field)
        if val is not None and not isinstance(val, bool):
            return False, f"{prefix}: {field} 必须是布尔值"

    return True, None

#   校验包大小相关字段，属于业务流校验的一部分
def _validate_packet_size(flow: dict, prefix: str) -> bool:
    """校验包大小相关字段"""
    has_size = "packet_size" in flow
    has_min = "packet_size_min" in flow
    has_max = "packet_size_max" in flow

    # 检查单个字段范围
    for field in ["packet_size", "packet_size_min", "packet_size_max"]:
        val = flow.get(field)
        if val is not None:
            if not isinstance(val, int) or not (40 <= val <= 9216):
                return False

    # 如果同时有 min/max，min ≤ max
    if has_min and has_max:
        if flow["packet_size_min"] > flow["packet_size_max"]:
            return False

    return True

#   校验业务占比：所有 sender flow 的 rate_percent 之和必须为 100
def _validate_rate_percent(flows: list, config: dict) -> Tuple[bool, Optional[str]]:
    """校验业务占比：所有 sender flow 的 rate_percent 之和必须为 100"""
    total_rate = config.get("total_rate_mbps")

    sender_percents = []
    for i, flow in enumerate(flows):
        if flow.get("role") == "sender" and "rate_percent" in flow:
            sender_percents.append((i, flow["rate_percent"]))

    if len(sender_percents) == 0:
        # 没有使用 rate_percent 的 flow，无需校验
        return True, None

    if total_rate is None:
        return False, "使用了 rate_percent 但缺少 total_rate_mbps"

    pct_sum = sum(p for _, p in sender_percents)
    # 允许浮点误差
    if abs(pct_sum - 100.0) > 0.01:
        return False, f"所有 sender 的 rate_percent 之和为 {pct_sum}, 必须为 100"

    return True, None

# ── 便捷函数 ──────────────────────────────────────────
# 业务占比：当顶层配置 total_rate_mbps 且所有发送流配置 rate_percent 时
#代理端按照「子流目标速率 = 总速率 × 业务占比 ÷ 100」计算 target_rate_mbps。

def calculate_target_rates(flows: list, total_rate_mbps: float) -> list:
    """
    根据 total_rate_mbps 和 rate_percent 自动计算各 sender flow 的 target_rate_mbps。
    返回更新后的 flows 列表（浅拷贝）。
    """
    result = [dict(f) for f in flows]
    for flow in result:
        if flow.get("role") == "sender" and "rate_percent" in flow:
            flow["target_rate_mbps"] = total_rate_mbps * flow["rate_percent"] / 100.0
    return result