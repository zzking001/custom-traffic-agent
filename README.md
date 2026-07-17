# 自定义流量生成工具 — 代理端

基于《自定义流量生成工具代理端通信协议与数据帧格式》文档实现的代理端协议函数库。

## 项目结构

```
custom-traffic-agent/
├── agent_core/              # 核心函数库（独立，可被框架引用）
│   ├── __init__.py
│   ├── crc.py               # CRC32 校验 (ISO-HDLC)
│   ├── protocol.py          # 控制帧 + 40字节数据头 打包/解包
│   ├── payload.py           # 测试载荷生成 (counter/zero/random/hex)
│   ├── config_validator.py  # START JSON 配置校验 + 业务占比计算
│   ├── traffic_models.py    # 6种流量模型 (cbr/poisson/markov/regression/burst/step)
│   └── statistics.py        # 时延/抖动/丢包/乱序 统计计算
├── tests/                   # 单元测试
│   ├── test_crc.py
│   ├── test_protocol.py
│   ├── test_payload.py
│   ├── test_config_validator.py
│   ├── test_traffic_models.py
│   └── test_statistics.py
└── README.md
```

## 环境要求

| 项 | 说明 |
|---|---|
| **操作系统** | Ubuntu 20.04+（实际运行环境） |
| **Python** | 3.10+ |
| **依赖** | 标准库（`struct`, `binascii`, `json`, `math`, `random`, `os`），无第三方库 |
| **测试** | `pytest` |

```bash
# 安装测试依赖
pip3 install pytest

# 运行全部测试
python3 -m pytest tests/ -v
```

## ✅ 已完成

6 个模块，79 个测试，全部通过。

| 模块 | 功能 | 测试数 | 文档章节 |
|---|---|---|---|
| `crc.py` | CRC32 校验（多项式 0x04C11DB7） | 6 | §3 |
| `protocol.py` | 控制帧打包/解包 + 数据头打包/解包 | 17 | §4, §9 |
| `payload.py` | payload 生成（counter/zero/random/hex） | 11 | §5.2 |
| `config_validator.py` | START 配置 JSON 字段校验 + 业务占比计算 | 18 | §5 |
| `traffic_models.py` | cbr / poisson / markov / regression / burst / step | 15 | §6 |
| `statistics.py` | 时延(P95/P99)、抖动、丢包估算、乱序/重复检测 | 12 | §8, §10 |

## 🟡 待完成（依赖师兄框架）

以下功能模块的函数体已明确，但需要框架提供调用约定：

- UDP 58888 监听 + 命令分发（START/STOP/QUERY/CLEAR/CAPABILITY）
- TaskManager 多任务管理 + 状态机
- Sender worker 主循环（发包 + 速率控制）
- Receiver worker 主循环（收包 + 统计）
- 资源管理器（端口/带宽冲突检测）
- 设备发现协议（UDP 51201，沿用现有）
- 资源上报（UDP 59999，沿用现有）
- EVENT_COMPLETED 异步推送

## 🔴 待确认

需和师兄确认的问题：

1. **CAPABILITY 应答字段名** — 管理端是否有固定预期？
2. **Markov transition_matrix 格式** — 二维数组还是扁平？
3. **Regression sine 参数结构** — `{amplitude, period_s, phase}`？
4. **TCP 下流量模型语义** — 硬限速还是尽力而为？
5. **`payload_pattern "hex:..."` 语法** — 按模板长度还是填满 payload_len？
6. **`report_interval_ms` 一期是否实现** — 文档标注为"预留"

## 设计要点

- **多任务架构**：每个 task_id 独立状态机，BUSY 仅在资源冲突时返回
- **字节序**：全部大端序（网络字节序）
- **帧结构**：15+N 字节控制帧，40 字节固定数据头
- **CRC**：ISO-HDLC 标准，初始值与异或值均为 0xFFFFFFFF
- **运行平台**：Ubuntu Linux（网卡命名 eth/ens、VLAN 子接口、SO_PRIORITY 等）
