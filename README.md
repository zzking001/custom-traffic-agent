# 自定义流量生成工具 — 代理端协议函数库

基于《自定义流量生成工具代理端通信协议与数据帧格式》文档实现的协议层函数库。

**职责边界**：只做协议相关的数据编解码、校验和算法计算。不涉及 socket 通信、线程管理、任务调度——这些属于师兄框架的部分。

---

## 核心概念速览

### 两种速率，两个模块

| | 目标速率 | 实际速率 |
|---|---|---|
| **谁算的** | `traffic_models.py` | `statistics.py` |
| **是什么** | 我想发多快 | 实际发了/收了多少 |
| **在哪里** | 发送端 | 发送端 + 接收端 |
| **用途** | 控制发包节奏 | 测试结束后对比目标值，验证网络质量 |

### 三种帧，都在 protocol.py

| 帧类型 | 用途 | 走的网络 |
|---|---|---|
| **控制帧** (15+N 字节) | 管理端 ↔ 代理端，命令与应答 | 管理网络 UDP 58888 |
| **数据头** (40 字节) | 代理端 ↔ 代理端，测试流量标识 | 100G 测试网络 |
| **测试载荷** (0~9176 字节) | 填充测试报文内容 | 100G 测试网络 |

### 完整报文结构

```
┌────────────── 40 字节数据头 ──────────────┬── 0~9176 字节载荷 ──┐
│ magic/version/flow_id/sequence/ts/CRC... │  counter/zero/...    │
│                                         │                      │
│         protocol.py 负责                 │   payload.py 负责    │
└──────────────────────────────────────────┴──────────────────────┘
│←────────────── packet_size = 头 40 + 载荷 N ─────────────────→│
```

---

## 项目结构

```
custom-traffic-agent/
├── agent_core/              # 核心函数库（纯算法，不依赖框架）
│   ├── crc.py               # CRC32 校验
│   ├── protocol.py          # 控制帧 + 数据头 编解码
│   ├── payload.py           # 测试载荷生成
│   ├── config_validator.py  # START 配置校验 + 业务占比计算
│   ├── traffic_models.py    # 6 种流量模型
│   └── statistics.py        # 时延/抖动/丢包/乱序统计
├── tests/                   # 单元测试（79 个，全通过）
└── .git/
```

## 模块详解

### 1. `crc.py` — CRC32 校验

**文档来源**：§3 通用编码规则

**为什么需要**：文档要求所有帧都带 CRC32 校验，确保传输过程中数据不被损坏。控制帧和数据头各有一个 CRC 字段。

**三个函数**：

| 函数 | 用途 |
|---|---|
| `crc32(data) → int` | 计算 CRC32 值 |
| `crc32_bytes(data) → bytes` | 同上，直接返回 4 字节大端序，打包帧时用 |
| `verify_crc(data, expected)` | 解包时验证 CRC 是否正确 |

**被谁调用**：只有 `protocol.py`。任何需要 CRC 的地方都通过 protocol 间接使用。

**实现**：Python 标准库 `binascii.crc32` 恰好就是 ISO-HDLC 算法，一行代码搞定。

---

### 2. `protocol.py` — 控制帧 + 数据头编解码

**文档来源**：§4 控制帧格式 + §9 测试数据报文格式

**为什么需要**：协议规定帧有严格的二进制格式（字节偏移、大端序），手动拼接容易出错。用 struct + 校验逻辑封装后，调用方只需要关心字段值。

**函数清单**：

| 函数 | 方向 | 用途 |
|---|---|---|
| `pack_frame(action, flags, task_id, payload)` | 打包 | 构造控制帧，返回 bytes |
| `pack_frame_with_preamble(...)` | 打包 | 同上，前加 0xAA 兼容包头 |
| `unpack_frame(data)` | 解包 | 拆控制帧，返回 dict，自动校验 |
| `pack_data_header(task_id, flow_id, ...)` | 打包 | 构造 40 字节数据头 |
| `unpack_data_header(data)` | 解包 | 拆数据头，返回 dict |

**设计要点**：
- `unpack_frame` 对 CRC 错误不抛异常，只标记 `crc_valid=False`——调用方可以拿到帧的其他字段来判断"是不是发给我的但路上损坏了"
- `pack_frame_with_preamble` 中的 0xAA 不参与 CRC，文档规定分发前移除
- 数据头格式串 `!4s B B H I H B B Q Q H H` 就是文档 §9 表的逐行翻译

---

### 3. `payload.py` — 测试载荷生成

**文档来源**：§5.2 的 `payload_pattern` 字段 + §9 报文格式

**为什么需要**：测试报文需要填充内容。管理端指定 pattern（counter/zero/random/hex），发送端据此生成对应 bytes。

**唯一入口**：`generate_payload(length, pattern) → bytes`

**四种模式**：

| pattern | 生成方式 | 用途 |
|---|---|---|
| `"zero"` | 全 0 | 纯带宽测试 |
| `"counter"` | 4 字节大端递增 | 发送端可验证载荷完整性 |
| `"random"` | `os.urandom()` | 模拟真实业务，防止网络设备压缩优化 |
| `"hex:..."` | 十六进制模板循环填充 | 特定比特模式测试 |

**数据流中的位置**：
```
sender worker:
  header = pack_data_header(..., payload_len=160)
  body   = generate_payload(160, "counter")
  packet = header + body          ← 完整报文
  sock.sendto(packet, dest)
```

---

### 4. `config_validator.py` — START 配置校验

**文档来源**：§5 全部字段定义（顶层 + 逐流 + 条件必填）

**为什么需要**：代理端不能信任管理端发来的任何配置。在启动任务前把所有字段校验完，返回明确的错误原因，比跑一半炸了再排查快得多。

**入口**：`validate_task_config(config) → (True, None)` 或 `(False, "错误原因")`

**校验三层结构**：

```
validate_task_config()
  ├── _validate_top_level()    # §5.1 顶层字段：duration_s,task_name,start_delay_ms...
  ├── _validate_flow() × N     # §5.2 逐流字段：flow_id,role,速率,包大小,PCP,DSCP...
  │     └── _validate_packet_size()  # 包大小范围 + min≤max
  └── _validate_rate_percent() # 跨 flow：所有 sender 的 rate_percent 之和=100
```

**条件必填举例**：
- receiver 必填 `local_port`
- sender 必填 `destination_ip` + `destination_port`
- sender 的 `target_rate_mbps` 和 `rate_percent` 必须至少有一个

**额外工具**：`calculate_target_rates(flows, total_rate_mbps)` — 文档 §6 公式"子流目标速率 = 总速率 × 业务占比 ÷ 100"的实现。校验与计算分离，互不污染。

---

### 5. `traffic_models.py` — 流量模型

**文档来源**：§6 六种流量模型的定义和生成规则

**为什么需要**：真实网络流量不是匀速的。不同业务特征各异（突发、阶梯加压、周期性波动），需要用不同模型模拟。

**两个公开函数**：

| 函数 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `calc_rate(model, elapsed_s)` | 模型配置 + 已运行秒数 | 当前瞬时速率 (Mbps) | 告诉 sender "现在该发多快" |
| `calc_interval(model, pkt_size, elapsed_s)` | 同上 + 包大小 | 发包间隔 (秒) | 告诉 sender "发完这个包等多久再发下一个" |

**六种模型**：

| 模型 | 核心逻辑 | 模拟场景 |
|---|---|---|
| **cbr** | 始终返回固定速率 | 稳定背景流量 |
| **poisson** | 返回平均速率，随机间隔由 sender worker 生成 | 独立随机到达 |
| **burst** | `elapsed % period < burst_dur` 则峰值，否则基线 | 突发数据、PFC 验证 |
| **step** | 遍历 stages，找 `offset_s ≤ elapsed_s` 的最大阶段 | 阶梯加压测试 |
| **regression** | 线性项 + 时间趋势 + 正弦周期，最终限幅 | 多因素相关业务 |
| **markov** | 首次初始化状态，按周期 + 转移矩阵随机切换 | 工作模式切换 |

**Markov 状态管理**：在 `config` dict 上挂 `_markov_state` 和 `_markov_last_switch`，避免调用方单独维护状态对象。这是模块内唯一有状态的设计。

---

### 6. `statistics.py` — 接收端统计

**文档来源**：§8.3 逐流结果字段 + §10 统计口径

**为什么需要**：接收端收到数据包后，需要根据包头信息计算丢包率、时延、抖动等指标，最终填入 §8 格式的结果 JSON 返回管理端。

**两个纯函数 + 一个有状态类**：

| 组件 | 类型 | 用途 |
|---|---|---|
| `compute_latency_stats(samples)` | 纯函数 | 计算 avg/min/max/P95/P99 时延 |
| `compute_jitter(samples)` | 纯函数 | 计算相邻时延差值的 avg/max |
| `SequenceTracker` | 有状态类 | 边收包边追踪序号，检测丢包/重复/乱序 |

**SequenceTracker 工作原理**：

```
每收到一个包，调用 feed(seq):

1. seq 之前见过？ → 重复包 +1
2. seq < 之前最大序号？ → 乱序包 +1
3. seq > seq_max？ → 中间空隙 = 丢包，更新 seq_max

任务结束调用 estimate_loss():
  expected = seq_max + 1（序号从 0 开始）
  loss_pct = lost / expected × 100
```

**时延样本上限**：文档 §10 规定最多保留 10000 个样本用于 P95/P99。高速测试（100Gbps 小包）每秒上亿个包，不限制会导致内存爆炸。

**时延有效性前提**：两端必须先做高精度时钟同步（PTP），否则单向时延和抖动不可作为有效结论。吞吐量、包数、CRC、丢包、乱序统计不受影响。

---

## 模块依赖关系

```
crc.py              ← 最底层，无依赖
    │
    └── protocol.py ← 依赖 crc.py
            │
            ├── sender worker:
            │     ┌── traffic_models.py (无依赖)
            │     └── payload.py        (无依赖)
            │
            └── receiver worker:
                  └── statistics.py     (无依赖)

config_validator.py  ← 独立，无依赖，被 TaskManager 调用
```

## 数据流全景

```
管理端 ──START JSON──▶ 代理端
                         │
                    unpack_frame()          [protocol.py]
                         │
                    validate_task_config()  [config_validator.py]
                         │ True
                    ACCEPTED
                         │
              ┌──────────┴──────────┐
              │                     │
         sender worker        receiver worker
              │                     │
         calc_rate()           recvfrom()
         calc_interval()       unpack_data_header()  [protocol.py]
         [traffic_models.py]        │
              │                latency = now - ts
         pack_data_header()    feed(seq)              [statistics.py]
         [protocol.py]              │
              │                任务结束:
         generate_payload()    compute_latency_stats()
         [payload.py]          compute_jitter()
              │                estimate_loss()        [statistics.py]
         sendto()                   │
              │                构建结果 JSON → 管理端
              ▼
        100G 测试网络 ──────────▶ 对端
```

---

## 环境要求

| 项 | 说明 |
|---|---|
| **实际运行平台** | Ubuntu 20.04+ |
| **开发平台** | Windows + VSCode SSH |
| **Python** | 3.10+ |
| **第三方依赖** | 无（仅使用标准库 struct/binascii/json/math/random/os） |
| **测试** | `pytest` |

```bash
pip3 install pytest
python3 -m pytest tests/ -v    # 79 tests, 全通过
```

## 待对接（师兄框架）

- UDP 58888 监听 + 命令分发（START/STOP/QUERY/CLEAR/CAPABILITY）
- TaskManager 多任务管理 + 资源冲突检测
- sender/receiver worker 主循环
- 设备发现协议（UDP 51201）
- 资源上报（UDP 59999）

## 待确认问题

1. CAPABILITY 应答字段名
2. Markov transition_matrix / Regression sine 参数的精确 JSON 格式
3. TCP 下流量模型语义（硬限速 vs 尽力）
4. `payload_pattern "hex:..."` 的长度语义
5. `report_interval_ms` 是否一期实现
