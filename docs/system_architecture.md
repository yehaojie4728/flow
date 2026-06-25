# FlowGap 系统架构文档

> 更新日期：2026-06-23  
> 版本：v1.0（对应实验结果 commit fc2b0d6）

---

## 1. 系统概述

FlowGap 是一个面向 Ascend NPU 集群的**预测式探针调度系统**，核心思想是：利用 eBPF 实时采集 `aclrtMemcpy` 传输间隙（gap）的统计特征，通过 GBDT 模型预测下一个安全探针窗口，在不干扰训练任务的前提下执行带宽/延迟探针，实现对 NPU 间链路（HCCS Fabric）的持续性能监控与故障检测。

**设计目标**：
- 零干扰：探针仅在预测到安全间隙时触发，不占用训练带宽
- 低延迟：在线预测延迟 < 1ms，探针执行延迟 avg 101 µs
- 高精度：间隙预测 precision 95–97%，FSR（假安全率）< 2%
- 跨负载：框架在训练（GLM-6B）和推理（Qwen2-7B）负载上均有效

---

## 2. 整体架构

系统分为两个阶段和五个核心模块：

```
┌─────────────────────────────────────────────────────────────────────┐
│  Training Process (GLM-6B / Qwen2-7B)                              │
│  Ascend 910A NPU × 8   ←→   aclrtMemcpy()   ←→   HCCS Fabric      │
└───────────────────────┬─────────────────────────────────────────────┘
                        │ memcpy events (uprobe)
┌───────────────────────▼─────────────────────────────────────────────┐
│  FlowGap Agent                                                      │
│                                                                     │
│  ┌─── Offline Phase ───────────────┐  ┌─── Online Phase ─────────┐ │
│  │  eBPF Tracer                    │  │  Gap Predictor            │ │
│  │  Trace Parser                   │  │  Probe Scheduler          │ │
│  │  Feature Extractor              │  │  Probe Executor           │ │
│  │  GBDT Trainer  ─── model ──────►│  │                           │ │
│  └─────────────────────────────────┘  └──────────┬────────────────┘ │
└──────────────────────────────────────────────────┼─────────────────┘
                                                   │ metrics
                                          ┌────────▼────────┐
                                          │   Diagnosis      │
                                          │  (Bottleneck /   │
                                          │   BW / Latency)  │
                                          └─────────────────┘
```

---

## 3. 硬件层

### 3.1 Ascend 910A NPU

| 参数 | 值 |
|------|-----|
| NPU 数量 | 8（设备号 /dev/davinci0–7） |
| 互联总线 | HCCS Fabric（高速片间通信） |
| 驱动版本 | CANN 8.0.RC3 |
| 容器挂载 | `/dev/davinci_manager`, `/dev/devmm_svm`, `/dev/hisi_hdc` |

### 3.2 内存传输接口

FlowGap 的核心采集目标是 `aclrtMemcpy`，其调用签名：

```c
aclError aclrtMemcpy(void *dst, size_t destMax,
                     const void *src, size_t count,
                     aclrtMemcpyKind kind);
```

`kind` 编码传输方向：
- `0` = Host→Host
- `1` = **Host→Device**（权重加载、推理输入）
- `2` = **Device→Host**（梯度回传、诊断读取）
- `3` = Device→Device（NPU 间 HCCS 传输）

训练场景以 `kind=1/2` 为主，推理以 `kind=1` 为主。

---

## 4. 数据采集层（eBPF Tracer）

### 4.1 实现方式

文件：`code/ebpf_monitor/trace_memcpy_numa.py`

使用 Linux eBPF uprobe 技术，在用户态动态插桩 `libascendcl.so` 中的两个符号：

```
aclrtSetDevice  →  trace_set_device()   # 追踪每个线程的当前设备号
aclrtMemcpy     →  probe_entry()        # 函数入口：记录起始时间戳 + 参数
                →  probe_return()       # 函数返回：计算耗时，推送事件
```

关键设计：
- 使用 `BPF_HASH(thread_device)` 跟踪每线程设备绑定，解决多 NPU 并发问题
- 事件通过 `BPF_PERF_OUTPUT` 异步推送到用户态，最小化内核态开销
- 支持 `--min-size` 过滤小传输，默认 1MB

### 4.2 NUMA 感知

通过 `/proc/<pid>/task/<tid>/stat` 中的 CPU 编号字段反查 `/sys/devices/system/cpu/cpuN/nodeN` 获得 NUMA 节点，输出格式为 `Host(NUMA X) → NPU Y`。

### 4.3 输出格式

```csv
PID,TID,Source,Destination,Size_MB,Latency_us,Bandwidth_GBps,
Start_ns,End_ns,WallStart_ns,WallEnd_ns
```

聚合输出（`.agg` 文件）通过重叠区间合并（overlap-merge）将同 src→dst 方向的连续传输聚合为窗口：

```csv
WindowStart_ns,WindowEnd_ns,Source,Destination,Bytes_MB,
Bandwidth_GBps,WindowStartWall_ns,WindowEndWall_ns,Duration_ms,Packet_Count
```

### 4.4 实测性能开销（P1.3）

| 指标 | 数值 |
|------|------|
| 系统 CPU 开销均值 Δ | +1.17 pp |
| 系统 CPU 开销中位数 Δ | +0.075 pp |
| Tracer 进程自身 CPU | 0.002% |

eBPF tracer 对系统 CPU 的影响可忽略不计。

---

## 5. 离线训练流水线

### 5.1 Trace Parser

文件：`code/trace_parser/parse_trace.py`、`intervalize.py`

**输入**：eBPF 采集的 CSV log  
**输出**：`FlowEvent` 对象列表，按 `(src, dst, kind)` 路径分组

核心步骤：
1. 解析 CSV，构建 `FlowEvent(pid, tid, src, dst, size_bytes, start_ns, end_ns, kind)`
2. `group_by_path()` 按传输路径分组
3. `build_timeline(events, busy_threshold_ns, gap_threshold_ns, path_id)` 将事件序列转为 `busy_interval[]` 和 `gap_interval[]` 两个时间线

已通过 38 个单元测试验证。

### 5.2 Feature Extractor

**滑动窗口大小**：WIN=50（训练），WIN=10（小数据集兼容模式）

每个样本提取 **30 维特征**，分为六组：

| 特征组 | 特征 | 维度 |
|--------|------|------|
| Gap 统计 | p10/p50/p90/mean/std/last/last5_mean | 7 |
| Burst 统计 | p50/p90/mean/rate/last_duration | 5 |
| 上下文 | idle_age_ns, time_since_last_sync, phase_id, sync_before_flag | 4 |
| 拓扑 | path_id_norm, direction_code, cross_numa_flag, stream_id_norm, stream_pending | 5 |
| 系统状态 | cpu_usage_pct, npu_util_pct, ebpf_event_rate, drop_rate, unknown_path_ratio | 5 |
| 不确定性 | async_uncertainty, timestamp_jitter, hour_of_day, workload_runtime | 4 |

**标签**：对每个预测 horizon `h`，`y = (gap_duration_ns >= h)` 为二分类标签。

### 5.3 GBDT Trainer

**模型**：`GradientBoostingClassifier`（scikit-learn）

| 超参数 | 值 |
|--------|-----|
| n_estimators | 50（快速训练），完整版 200 |
| max_depth | 4 |
| learning_rate | 0.1 |
| subsample | 0.8 |
| random_state | 42 |

**预测 Horizon（8个）**：
- 短：50µs, 100µs, 250µs
- 中：500µs, 1ms, 2ms
- 长：5.1ms, 10ms

模型持久化：`models/gbdt_pass1.pkl`（879 KB，包含 8 个 horizon 的独立分类器）

---

## 6. 在线运行循环

### 6.1 数据流

```
tail eBPF log
    → parse latest events
    → extract sliding window features (30-dim)
    → GBDT predict: P(next_gap >= h) for each horizon h
    → Probe Scheduler: select optimal probe window
    → Probe Executor: execute via AscendCL
    → record results → feedback to scheduler
```

### 6.2 Gap Predictor

- **输入**：最新 WIN 个间隙事件的 30 维特征向量
- **输出**：各 horizon 的概率 `P(gap >= h)`，置信度阈值 η（默认 0.5）
- **延迟**：GBDT 单次推理 < 1ms（CPU）

### 6.3 Probe Scheduler（flowgap_predictive 策略）

核心逻辑：当预测的间隙概率超过阈值时，触发探针。支持 7 种对比策略：

| 策略 | 描述 |
|------|------|
| `flowgap_predictive` | GBDT 预测 + 置信度门控（本文方法） |
| `fixed_interval` | 固定周期触发 |
| `random` | 随机触发 |
| `threshold` | 基于最近间隙阈值 |
| `ewma_only` | 指数加权移动平均 |
| `oracle` | 完美预知（上界） |
| `never` | 不触发（基准） |

### 6.4 Probe Executor

文件：`code/probe_executor/`

**实现方式**：AscendCL C API via Python ctypes，不依赖 MindSpore/PyTorch 框架。

**探针类型**：

**延迟探针（Latency Probe）**：
- 分配 1KB Host/Device buffer
- 触发一次 `aclrtMemcpyAsync`，测量 round-trip 延迟
- 实测：avg 101 µs，范围 24–167 µs

**带宽探针（Bandwidth Probe）**：
- 分配 128MB–256MB buffer
- 多次传输取平均，计算有效带宽
- 实测：avg 19.3 GB/s，范围 14.4–20.8 GB/s

**关键设计**：
- 使用**独立 AscendCL stream**，与训练 stream 隔离
- 探针执行后通过 `aclrtSynchronizeStream` 等待完成
- 已通过 9 个 NPU 真机测试验证

---

## 7. 实验结果汇总

### 7.1 RQ1 — 间隙可预测性（GLM-6B，Pass1→Pass2 跨轮验证）

| Horizon | Precision | Recall | FSR | Brier |
|---------|-----------|--------|-----|-------|
| 250µs | 0.95–0.97 | — | <2% | — |
| 500µs | 见 P0.2 详细结果 | | | |

### 7.2 P1.2 — 跨负载泛化（Qwen2-7B，5-fold CV）

| Horizon | Precision | Recall | FSR | Brier | N |
|---------|-----------|--------|-----|-------|---|
| 500µs | 0.975 | 1.000 | 0.055 | 0.018 | 162 |
| 5.1ms | 0.951 | 0.952 | 0.050 | 0.037 | 162 |

### 7.3 在线验证（GLM-6B 完整训练）

| 指标 | 数值 |
|------|------|
| 总探针次数 | 488 次 |
| 延迟探针 | 385 次 |
| 带宽探针 | 103 次 |
| 错误次数 | 0 |

---

## 8. 关键数据文件

| 文件 | 描述 |
|------|------|
| `data/collected/pass1_ebpf.log` | GLM-6B Pass1 eBPF trace |
| `data/collected/pass2_raw.log` | GLM-6B Pass2 eBPF trace（37万行） |
| `data/collected/qwen2_7b_mindie/qwen2_memcpy.log` | Qwen2-7B MindIE 推理 trace（203条） |
| `data/processed/burst_gap_events.parquet` | GLM-6B 特征数据集 |
| `data/processed/burst_gap_events_qwen2.parquet` | Qwen2-7B 特征数据集（162行） |
| `models/gbdt_pass1.pkl` | 离线训练模型（879 KB，8 horizon） |

---

## 9. 部署环境

| 组件 | 版本 |
|------|------|
| 硬件 | Ascend 910A（aarch64），bms-9002 |
| 驱动 | CANN 8.0.RC3 |
| 推理容器 | MindIE 1.0.T65（镜像：swr.cn-central-221...mindie:910a-...） |
| eBPF 运行时 | bpfcc（Python 3.7，EulerOS 2.0 SP10） |
| 训练环境 | conda `mindspore_py37`（MindSpore 2.2.14 + NNAE 7.0.0） |
| ML 分析环境 | conda `flowgap`（Python 3.x，scikit-learn，pandas，matplotlib） |

---

## 10. 待完成实验（Roadmap）

| 编号 | 实验 | 状态 | 需要服务器 |
|------|------|------|------------|
| P0.1 | 7策略对比 — 安全率排名 | ✅ 完成 | 否 |
| P0.2 | 预测准确性完整评估 | ✅ 完成 | 否 |
| P0.3 | 训练开销测量（有/无探针） | ✅ 完成 | 是 |
| P0.4 | 故障注入 + 检测验证 | ✅ 完成 | 是 |
| P1.1 | 特征消融 | ✅ 完成 | 否 |
| P1.2 | 第二负载验证（Qwen2-7B） | ✅ 完成 | — |
| P1.3 | eBPF 开销测量 | ✅ 完成 | 是 |
| P1.4 | 参数敏感性分析 | ✅ 完成 | 否 |
| P2.1 | 冷启动分析 | ✅ 完成 | 否 |
| P2.2 | 在线 drift 分析 | ✅ 完成 | 否 |
| P2.3 | Oracle 上界对比 | ✅ 完成 | 否 |
