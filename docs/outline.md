# FlowGap 论文大纲：基于流量模式预测的低干扰主机内探测系统

> 面向 Ascend 910A/910B memcpy traffic 的自适应探测时机选择机制  
> 核心目标：通过 eBPF 感知 Ascend 主机内 memcpy 事件，预测未来空闲时间/空闲链路，在预测出的安全窗口中触发 probe，从而降低探测对 AI workload 的干扰。

---

## 0. 论文定位

### 0.1 一句话问题定义

现有主机内主动探测系统能够发现链路瓶颈，但在 Ascend AI workload 运行过程中，probe 本身可能与 memcpy burst 竞争 PCIe、HCCS、NUMA memory channel 等资源，导致 workload slowdown、collective jitter 和误判。因此，本文不再把重点放在“如何完整诊断所有瓶颈”，而是关注一个更基础的问题：

> **如何预测业务流量的空闲窗口，并只在高置信度空闲窗口中发起主机内探测？**

### 0.2 论文主线

```text
eBPF 采集 memcpy/sync 事件
        ↓
构建 path/link 级 busy-idle 时间线
        ↓
预测未来 safe window
        ↓
在 safe window 中发起 probe
        ↓
分析 probe 结果并反馈给预测器
```

### 0.3 系统模块

本文系统由三个模块组成：

1. **预测器 Predictor**
   - 通过 eBPF 获取 Ascend runtime 中的 memcpy、sync、device/memory allocation 等事件。
   - 将原始事件转换为 path/link 级 busy-idle 表示。
   - 使用轻量级、可解释、可在线校准的模型预测未来空闲时间窗口。
   - 输出 safe window、候选链路/path、预测空闲下界和置信度。

2. **探测器 Prober**
   - 在预测器给出的高置信度窗口中执行 latency probe 或 bandwidth probe。
   - 根据窗口大小选择 probe size、probe path 和 probe 类型。
   - 支持延迟、取消、降级 probe。

3. **分析器 Analyzer**
   - 分析 probe 结果，判断是否出现异常链路性能。
   - 与预测器反馈闭环：probe 是否与业务流量重叠、probe 实际耗时、窗口是否提前结束。
   - 后续可扩展为 fault localization，但本文重点不放在完整 root cause diagnosis。

### 0.4 与 Hostping / HostDiag 的关系

- **Hostping** 证明了主机内 latency/bandwidth 主动探测对发现 intra-host bottleneck 有价值，但它主要面向 RDMA server 和 RNIC loopback，并使用硬件状态或异常指标决定何时启动探测。
- **HostDiag** 将 Hostping 思路迁移到异构 AI accelerator 场景，使用 eBPF hook 深度学习库和 AI accelerator runtime 中的关键 API，获取数据大小、发送端、接收端、开始时间、结束时间，并用 memcpy 形式进行跨平台 one-way probing。
- **本文 FlowGap** 不重复做完整诊断系统，而是针对 Ascend 910A/910B 的 memcpy traffic，解决 Hostping/HostDiag 中仍然存在的 probing window selection 问题：在业务流量 bursty、async、phase-dependent 的情况下，如何预测 probe 的低干扰时机。

---

## 1. Introduction

### 1.1 背景

AI accelerator 服务器中的主机内通信越来越重要。以 Ascend 910A/910B 为例，训练、推理、checkpoint、数据加载和 collective communication 会产生大量 host-to-device、device-to-host、device-to-device memcpy 流量。这些流量通常不是均匀到达，而是呈现以下特征：

- **bursty**：大量 memcpy 在短时间内集中发生；
- **phase-dependent**：memcpy 与 iteration、同步、checkpoint、数据加载等阶段相关；
- **synchronization-sensitive**：某些 memcpy 或 sync 阶段会影响整个 iteration 的尾延迟；
- **path-sensitive**：不同 NUMA、NPU、fabric、PCIe/HCCS 路径上的流量模式不同。

### 1.2 问题

主动探测可以测量主机内链路的 bandwidth 和 latency，但传统探测方式通常存在两类问题：

1. **固定周期探测**
   - 可能与业务 memcpy burst 重叠；
   - 造成额外资源竞争；
   - 对同步敏感的 AI workload 产生放大效应。

2. **阈值/异常触发探测**
   - 能减少无意义 probe，但仍然不知道“当前是否适合 probe”；
   - 在异常发生时盲目 probe 可能进一步干扰业务；
   - 对 async runtime 和 burst-gap traffic 的时机感知不足。

### 1.3 核心洞察

本文的核心洞察是：

> Ascend memcpy traffic 虽然 bursty，但并非随机。对于给定 workload，在短时间尺度内，memcpy burst 和 gap 具有可学习的时间模式。系统不需要准确重建所有主机内流量，只需要保守判断未来一段时间是否足够空闲以容纳 probe。

因此，本文将主动探测从：

```text
periodic probing / threshold-triggered probing
```

转化为：

```text
confidence-calibrated safe-window probing
```

### 1.4 贡献

建议写成三个贡献：

1. **提出面向 Ascend memcpy traffic 的 safe-window prediction 问题定义。**  
   将主机内探测时机选择建模为：给定最近的 memcpy event stream，预测某条 path/link 在未来 horizon 内保持空闲的概率。

2. **设计 FlowGap Predictor。**  
   FlowGap 使用 eBPF 获取 Ascend runtime 事件，通过 event-driven busy-idle intervalization 构建 path/link 级流量状态，并采用 phase-aware multi-horizon survival predictor 预测不同 probe horizon 下的安全概率。

3. **在 Ascend 910A/910B 上实现并系统评估。**  
   通过真实 workload、synthetic burst workload 和故障/干扰注入实验，验证 FlowGap 能降低 probe-burst overlap、降低训练/推理任务 slowdown，同时保持足够的异常检测能力。

### 1.5 关键图

**Figure 1: Motivation example**

内容：同一段 Ascend memcpy trace 上叠加 fixed probing 与 FlowGap probing。

图中应展示：

- memcpy burst 时间段；
- fixed probe 与 burst overlap；
- FlowGap probe 落在 gap 中；
- 右侧柱状图展示 workload slowdown 或 iteration p99 增加。

---

## 2. Background and Motivation

### 2.1 Ascend intra-host communication

简要介绍 Ascend 910A/910B 服务器内的通信路径：

- host DDR ↔ NPU HBM；
- NPU ↔ NPU；
- NUMA memory ↔ NPU；
- PCIe path；
- HCCS / NPU full-mesh interconnect；
- runtime-managed async memcpy；
- stream synchronization。

重点不是硬件细节，而是说明为什么这些通信对 probe 时机敏感。

### 2.2 eBPF-based event visibility

参考 HostDiag 的做法，eBPF 可以 hook AI accelerator runtime 层的关键 API，从而非侵入式获得 memcpy 流量事件。需要说明可以获取的信息包括：

- `size`：memcpy 数据大小；
- `src/dst`：发送端和接收端，可通过地址和 device-id 映射得到；
- `t_start/t_end`：调用开始和结束时间；
- `direction`：H2D、D2H、D2D；
- `stream`：异步 stream 信息；
- `sync`：stream synchronization 信息。

可 hook 的 Ascend API 包括：

- `aclrtSetDevice`
- `aclrtMallocHost`
- `aclrtMallocDevice`
- `aclrtMemcpy`
- `aclrtMemcpyAsync`
- `aclrtMemcpy2d`
- `aclrtMemcpy2dAsync`
- `aclrtSynchronizeStream`
- `aclrtFreeHost`
- `aclrtFree`

### 2.3 为什么已有探测机制不足

#### Hostping-style probing 的不足

Hostping 使用 loopback test 测量 RNIC 到 host endpoint 的 intra-host latency/bandwidth，适合发现 RDMA server 内部 bottleneck。但在 Ascend 场景中：

- 没有完全一致的 RNIC-GPU loopback 假设；
- 业务 memcpy traffic 本身就是主要竞争源；
- AI workload 的 burst-gap 时间模式对 probe 干扰影响极大；
- 只知道“异常时探测”还不够，需要知道“什么时候探测”。

#### HostDiag-style threshold probing 的不足

HostDiag 已经使用 eBPF 监控 DML throughput，并在吞吐异常或利用率处于某区间时触发 prober。但阈值触发仍然有局限：

- 阈值只能判断当前 busy/abnormal，不能预测未来 gap；
- bursty traffic 下，当前低利用率不代表接下来安全；
- async memcpy 的真实执行边界不完全等于 API 调用边界；
- threshold selection 对不同 workload 敏感。

### 2.4 关键观察

本节建议用实验 trace 支撑三个 observation。

#### Observation 1: memcpy traffic is bursty but structured

同一 workload 的 memcpy burst-gap pattern 在 iteration 之间具有相似性。

要展示：

- gap duration distribution；
- burst duration distribution；
- autocorrelation；
- iteration-aligned trace。

#### Observation 2: useful probe gaps exist, but fixed probing often misses them

空闲 gap 不是一直存在，但很多 workload 中存在足以容纳 latency probe 或 small bandwidth probe 的 gap。

要展示：

- 不同 probe size 对应的可用 gap 比例；
- fixed probing 命中 safe gap 的概率；
- oracle probing 的理论上限。

#### Observation 3: interference is dominated by timing, not only probe volume

相同 probe 数量下，落在 burst 内和落在 gap 内的影响不同。

要展示：

- fixed probing 与 gap-aware probing 的 probe count 相近；
- 但 overlap ratio 和 workload slowdown 差异明显。

### 2.5 本章图表

- **Figure 2:** Ascend 910A/910B intra-host topology and monitored paths。
- **Figure 3:** Memcpy burst-gap trace across several iterations。
- **Figure 4:** Fixed probe vs oracle-gap probe 的 overlap 和 slowdown 对比。

---

## 3. System Overview

### 3.1 目标

FlowGap 的目标不是替代完整诊断系统，而是作为 Hostping/HostDiag-style prober 的前置时机选择层：

> 给定一组候选 probe path，FlowGap 判断哪些 path 在未来一段时间内大概率空闲，并输出可安全探测的时间窗口。

### 3.2 非目标

需要明确说明本文不做以下事情：

- 不精确重建所有物理链路流量；
- 不依赖硬件计数器的完美可用性；
- 不保证预测每一次 memcpy 的精确开始时间；
- 不把完整 root cause localization 作为主要贡献；
- 不追求跨所有 accelerator 平台的通用实现，优先面向 Ascend 910A/910B。

### 3.3 架构

```text
+--------------------+
|  DML / AI Workload |
+---------+----------+
          |
          v
+--------------------+
| eBPF Event Monitor |
| memcpy / sync hook |
+---------+----------+
          |
          v
+----------------------------+
| Event Normalizer           |
| address -> device/path     |
| async interval estimation  |
+---------+------------------+
          |
          v
+----------------------------+
| FlowGap Predictor          |
| busy-idle timeline         |
| multi-horizon prediction   |
| confidence calibration     |
+---------+------------------+
          |
          v
+----------------------------+
| Prober                     |
| latency / bandwidth probe  |
| cancellation / downgrade   |
+---------+------------------+
          |
          v
+----------------------------+
| Analyzer                   |
| probe analysis             |
| feedback update            |
+----------------------------+
```

### 3.4 输出接口

预测器给探测器的输出建议定义为：

```text
SafeWindow {
    path_id,
    link_bitmap,
    t_publish,
    g_lower_bound,
    p_safe,
    confidence,
    allowed_probe_type,
    max_probe_size,
    reason_code
}
```

其中：

- `g_lower_bound` 是预测 gap 的保守下界，而不是平均值；
- `p_safe` 表示未来 horizon 内没有业务 memcpy 到达的概率；
- `confidence` 是综合置信度，包含模型概率、历史校准、数据质量和漂移检测；
- `allowed_probe_type` 可为 no probe、tiny latency probe、normal latency probe、bandwidth probe。

---

## 4. Predictor Design

> 本文设计重点。建议用 2.5–3 页写预测器。

### 4.1 eBPF event collection

#### 4.1.1 Hook points

基于 AscendCL runtime hook：

| 类型 | Ascend API | 作用 |
|---|---|---|
| Set device | `aclrtSetDevice` | 获取当前 device context |
| Host allocation | `aclrtMallocHost` | 建立 host address 到 NUMA/device context 的映射 |
| Device allocation | `aclrtMallocDevice` | 建立 device address 到 NPU id 的映射 |
| Sync memcpy | `aclrtMemcpy`, `aclrtMemcpy2d` | 获取同步 memcpy 的 size、src/dst、开始/结束时间 |
| Async memcpy | `aclrtMemcpyAsync`, `aclrtMemcpy2dAsync` | 获取异步 memcpy submit 时间、size、src/dst、stream |
| Stream sync | `aclrtSynchronizeStream` | 校准 async memcpy 的完成时间 |
| Free | `aclrtFreeHost`, `aclrtFree` | 删除 address mapping |

#### 4.1.2 Event record

建议事件结构：

```c
struct FlowEvent {
    u64 ts_enter_ns;
    u64 ts_exit_ns;
    u64 ts_submit_ns;
    u64 ts_end_est_ns;

    u32 pid;
    u32 tid;
    u64 stream_id;

    u32 src_dev;
    u32 dst_dev;
    u32 src_numa;
    u32 dst_numa;

    u64 size;
    u8  direction;     // H2D / D2H / D2D / H2H
    u8  async_flag;
    u8  api_type;

    u32 path_id;
    u64 link_bitmap;

    u32 quality_flags; // drop, unknown path, async uncertainty, timestamp jitter
};
```

### 4.2 Event-driven busy-idle representation

#### 4.2.1 为什么不用固定时间窗

固定时间窗会带来两个问题：

1. **窗口过大**：短 gap 被平均掉，无法定位 probe 发送时机；
2. **窗口过小**：噪声和 micro-gap 太多，模型容易误判。

因此本文不采用固定 bin 作为主表示，而采用 event-driven 表示。

#### 4.2.2 也不直接使用原始事件

原始事件之间可能存在很多微小间隔。这些 micro-gap 对预测 memcpy pattern 有意义，但对 probe 不一定有意义。如果一个 gap 小于最小 probe 耗时加安全裕量，则即使事件层面“空闲”，也不应该作为 safe window。

#### 4.2.3 Probe-aware intervalization

将原始事件转换为 busy interval：


i-th memcpy event:

\[
f_i = (t_i^s, t_i^e, size_i, dir_i, path_i, links_i)
\]

对每条 path/link 维护 busy interval 集合：

\[
I_l = \{[t_i^s, t_i^e] \mid l \in links_i\}
\]

相邻 busy interval 之间的 gap 为：

\[
g_i = t_{i+1}^{s} - t_i^{e}
\]

如果：

\[
g_i < T_{probe}^{min} + M
\]

则将两段 busy interval 合并，因为这个 gap 不足以容纳任何安全 probe。

这不是传统时间窗合并，而是 probe-aware 合并。

### 4.3 Async memcpy interval estimation

Ascend workload 中 async memcpy 很常见，因此预测器需要区分两条时间线：

#### 4.3.1 Conservative timeline

用于最终安全判断。

- 同步 memcpy：`t_start = API enter`，`t_end = API return`；
- 异步 memcpy：如果 completion 不可见，则使用 stream sync 返回时间作为保守上界。

优点：不容易把 busy 错判为 idle。  
缺点：可能过于保守，错过部分可用 gap。

#### 4.3.2 Estimated timeline

用于模型学习。

对 async memcpy 估计真实执行区间：

\[
\hat{t_i}^{start}=\max(t_i^{submit}, \hat{t}_{stream}^{last\_end})
\]

\[
\hat{t_i}^{end}=\hat{t_i}^{start}+\frac{size_i}{\hat{B}_{path,dir}}+\epsilon
\]

并用 `aclrtSynchronizeStream` 返回时间修正误差：

\[
error = t_{sync} - \hat{t}_{stream}^{last\_end}
\]

如果 error 持续变大，则提高 async safety margin。

### 4.4 Path-level and link-level prediction

#### 4.4.1 Path-level first

第一版以 path-level 预测为主：

- host NUMA node → NPU；
- NPU → host NUMA node；
- NPU → NPU；
- fabric 内 NPU D2D；
- cross-NUMA path。

原因：eBPF 事件天然提供 src/dst，path-level 更可靠。

#### 4.4.2 Link-level refinement

当拓扑映射可靠时，将 path 映射到逻辑链路集合：

\[
P(src,dst)=\{l_1,l_2,...,l_k\}
\]

对 probe path \(p\)，只有所有链路都安全时才认为 path 安全：

\[
P_{safe}(p)=\min_{l\in p} P_{safe}(l)
\]

使用 `min` 而不是乘积，是为了保守。

### 4.5 Prediction model

#### 4.5.1 推荐主模型：multi-horizon survival predictor

预测器不直接预测“下一次 memcpy 的精确时间”，而是预测：

\[
P(T_{next}>h\mid x_t)
\]

含义：在当前特征 \(x_t\) 下，未来 \(h\) 时间内没有业务 memcpy 到达的概率。

多个 horizon：

\[
H=\{10\mu s,25\mu s,50\mu s,100\mu s,250\mu s,500\mu s,1ms,2ms\}
\]

对每个 horizon 定义标签：

\[
y_h(t)=
\begin{cases}
1, & [t,t+h] \text{ 内没有目标 path/link 的业务 memcpy} \\
0, & [t,t+h] \text{ 内出现业务 memcpy}
\end{cases}
\]

模型输出：

\[
S(h\mid x_t)=P(y_h=1)
\]

探测器只需要根据 probe cost 选择对应 horizon：

\[
h=T_{probe}+M
\]

若：

\[
S(h\mid x_t)>\eta
\]

则认为可以 probe。

#### 4.5.2 特征设计

推荐特征：

1. **Recent traffic features**
   - 最近 K 个 gap；
   - 最近 K 个 burst duration；
   - gap mean / variance / p10 / p50 / p90；
   - burst mean / p90；
   - 最近 N 次 memcpy 总字节数；
   - 最近 N 次 memcpy event count；
   - 当前 idle age。

2. **Path / link features**
   - path id；
   - link bitmap；
   - direction；
   - src/dst NPU；
   - NUMA id；
   - fabric id；
   - 是否 cross-NUMA / cross-fabric。

3. **Stream features**
   - stream id；
   - 同一 stream 上一次 memcpy 距今时间；
   - stream pending 数；
   - 最近一次 stream sync 距今时间。

4. **Phase features**
   - iteration phase；
   - sync-after / sync-before；
   - checkpoint phase；
   - collective phase；
   - dataloader phase。

5. **Resource features**
   - CPU usage；
   - host memory usage；
   - NPU utilization；
   - HBM usage；
   - eBPF event rate。

6. **Data quality features**
   - ring buffer drop rate；
   - unknown path ratio；
   - async uncertainty；
   - timestamp jitter；
   - model drift score。

#### 4.5.3 模型选择

建议主文采用以下组合：

| 层级 | 模型 | 作用 |
|---|---|---|
| Tier 0 | phase-aware EWMA / quantile | 冷启动、fallback、baseline |
| Tier 1 | multi-horizon logistic / GBDT survival predictor | 主预测模型 |
| Tier 2 | semi-Markov state model | 解释状态、检测 phase change |
| Calibration | empirical calibration / conformal lower bound | 提高置信度可信度 |

不建议第一版用 LSTM/Transformer 作为主模型，原因：

- 运行开销高；
- 在线更新复杂；
- confidence 不易校准；
- 对系统论文而言解释性不足；
- 当前任务是 safe-window prediction，不是完整流量生成。

### 4.6 Confidence calibration

模型输出概率不能直接等价为真实置信度。建议定义综合置信度：

\[
C=\min(C_{model}, C_{calib}, C_{data}, C_{drift})
\]

其中：

- \(C_{model}\)：模型输出的 safe probability；
- \(C_{calib}\)：最近预测结果的经验校准；
- \(C_{data}\)：数据质量置信度；
- \(C_{drift}\)：workload pattern 是否发生漂移。

#### 4.6.1 Calibration table

维护不同概率区间的实际命中率：

| Predicted probability bin | Actual safe ratio |
|---|---|
| 0.90–0.95 | 0.87 |
| 0.95–0.98 | 0.94 |
| 0.98–1.00 | 0.97 |

调度器使用校准后的概率，而不是原始概率。

#### 4.6.2 Lower-bound gap prediction

即使模型预测平均 gap 为 \(\hat{G}\)，也不直接使用，而使用保守下界：

\[
\hat{G}^{lower}=\hat{G}-Q_{1-\delta}(|\hat{G}-G|)
\]

只有当：

\[
\hat{G}^{lower}>T_{probe}+M
\]

并且：

\[
C>\eta
\]

才允许 probe。

### 4.7 Predictor algorithm

```text
Algorithm 1: Confidence-Calibrated Safe Window Prediction

Input:
  eBPF event stream E
  topology map topo
  probe cost model T_probe(path, type)
  confidence threshold eta
  safety margin M

State:
  address_to_device map
  stream_last_end map
  per-path busy-idle timeline
  per-link busy-idle timeline
  survival predictors
  calibration table
  drift detector

For each eBPF event e:

  1. Normalize event
     - resolve src/dst device by address map
     - infer direction and path_id
     - map path_id to link_bitmap
     - attach quality_flags

  2. Estimate execution interval
     if e is synchronous:
         ts = e.enter_time
         te = e.return_time
     else:
         ts = max(e.submit_time, stream_last_end[e.stream])
         te = ts + e.size / B_hat[path, direction]
         te = te + async_margin

  3. Update busy-idle timeline
     - insert [ts, te] into all affected path/link timelines
     - merge gaps shorter than T_probe_min + M

  4. Extract features x_t
     - recent gaps/bursts
     - idle age
     - path/link/direction/stream/phase/resource features
     - data quality features

  5. Predict safe probability
     for each horizon h:
         S[h] = predictor[path].predict(x_t, h)

  6. Calibrate confidence
     C_model = S[T_probe + M]
     C_calib = calibration.lookup(C_model)
     C_data  = data_quality_score()
     C_drift = drift_score()
     C_final = min(C_model, C_calib, C_data, C_drift)

  7. Publish safe window
     G_lower = lower_bound_gap(x_t)
     if G_lower > T_probe + M and C_final > eta:
         publish SafeWindow(path, G_lower, C_final)
     else:
         suppress probing
```

---

## 5. Prober Design

> 本文可以简写，细节留到后续工作或下一版扩展。

### 5.1 Probe types

| Probe 类型 | 目标 | 特征 | 使用场景 |
|---|---|---|---|
| Tiny latency probe | 估计 path latency | 极小 size，耗时短 | 低置信度窗口、保守模式 |
| Normal latency probe | 稳定估计 latency | 小 size，多次重复 | 中等窗口 |
| Bandwidth probe | 估计 one-way bandwidth | 大 size，耗时更长 | 高置信度长 gap |
| Confirmation probe | 验证异常 | 小规模重复 | 分析器发现疑似异常后 |

### 5.2 Probe admission control

调度器接收 SafeWindow 后判断：

\[
T_{probe}(path,type)+M < \hat{G}^{lower}
\]

如果满足，则发送 probe。

### 5.3 Probe downgrade

根据置信度选择 probe 类型：

| Confidence | 行为 |
|---|---|
| \(C > 0.98\) | 允许 bandwidth probe |
| \(0.95 < C \leq 0.98\) | 允许 normal latency probe |
| \(0.90 < C \leq 0.95\) | 只允许 tiny latency probe |
| \(C \leq 0.90\) | 不 probe |

### 5.4 Probe cancellation

如果在 probe 提交前预测器发现新的 memcpy burst 即将发生：

- 取消 pending probe；
- 或降级 probe size；
- 或推迟到下一个窗口。

如果 probe 已经提交，则记录是否 overlap，并反馈给预测器。

---

## 6. Analyzer Design

> 本文中 Analyzer 主要用于证明低干扰 probe 没有牺牲检测能力，不需要展开完整 root cause diagnosis。

### 6.1 Analyzer inputs

- probe path；
- probe type；
- probe start/end timestamp；
- measured latency；
- measured bandwidth；
- predicted safe window；
- actual business memcpy timeline；
- whether probe overlaps with business traffic。

### 6.2 Analyzer outputs

- path latency/bandwidth 是否异常；
- probe result 是否可信；
- 是否需要 confirmation probe；
- 是否反馈 predictor 调整 safety margin；
- 是否进入 failure-aware probing mode。

### 6.3 Feedback to predictor

每次 probe 后反馈：

```text
Feedback {
    path_id,
    predicted_window,
    actual_idle_duration,
    overlap_flag,
    probe_duration,
    measured_latency,
    measured_bandwidth,
    prediction_error,
    workload_slowdown_hint
}
```

预测器根据反馈更新：

- probe cost model；
- confidence calibration；
- safety margin；
- async uncertainty；
- drift state。

---

## 7. Implementation

### 7.1 Platform

实现目标平台：

- Ascend 910A；
- Ascend 910B；
- Kunpeng 920 CPU；
- AArch64；
- EulerOS / Ubuntu；
- AscendCL / CANN runtime。

### 7.2 Predictor implementation

- eBPF 使用 bpfcc/libbpf hook user-space AscendCL runtime；
- ring buffer 输出 FlowEvent；
- user-space predictor daemon 维护 path/link timeline；
- per-path predictor 使用轻量模型；
- calibration table 在线更新；
- drift detector 使用 rolling statistics。

### 7.3 State maintained by predictor

| 状态 | 用途 |
|---|---|
| address_to_device map | 地址解析 src/dst device |
| stream_last_end | 估计 async 执行顺序 |
| path timeline | path-level busy-idle 判断 |
| link timeline | link-level conservative refinement |
| recent gap/burst ring buffer | 特征提取 |
| calibration bins | 置信度校准 |
| probe cost table | 估计不同 probe 类型耗时 |
| drift statistics | 检测 workload pattern 变化 |

### 7.4 Implementation table

建议论文中放一张表：

| Component | Function | Implementation |
|---|---|---|
| eBPF hooks | collect memcpy/sync events | bpfcc/libbpf uprobe |
| Event normalizer | address/device/path mapping | user-space daemon |
| Timeline builder | path/link busy-idle interval | lock-free ring buffer + interval map |
| Predictor | safe-window probability | EWMA + multi-horizon classifier |
| Calibrator | confidence correction | empirical bins + drift detector |
| Prober | active memcpy probe | AscendCL synchronous memcpy |
| Analyzer | result analysis and feedback | user-space module |

---

# 8. Evaluation Plan

> 本文最重要部分。建议至少占全文 35%–40%。实验必须证明三件事：
>
> 1. **流量 gap 可预测。**
> 2. **预测窗口真的降低 probe 与业务流量重叠。**
> 3. **低干扰 probe 没有明显降低异常检测能力。**

---

## 8.1 Research Questions

建议将 Evaluation 按 RQ 组织。

### RQ1: Ascend memcpy traffic 是否具有可预测的 burst-gap 模式？

目的：证明问题有基础，不是强行预测随机流量。

### RQ2: FlowGap 的 safe-window prediction 准确吗？

目的：证明预测器有效，尤其是 false-safe rate 低。

### RQ3: event-driven intervalization 是否优于固定时间窗和原始事件输入？

目的：回应“为什么不用简单时间窗”或者“为什么不直接喂原始事件”。

### RQ4: FlowGap 是否减少 probe 与业务 memcpy burst 的重叠？

目的：证明调度效果。

### RQ5: FlowGap 是否降低 AI workload 干扰？

目的：证明系统价值。

### RQ6: FlowGap 是否保持足够的异常检测能力？

目的：回应 reviewer 的核心质疑：少 probe 会不会漏掉故障？

### RQ7: FlowGap 在 workload drift、async uncertainty、event loss 下是否稳健？

目的：证明系统可部署。

### RQ8: FlowGap 的 CPU、内存、eBPF 采集开销是否可接受？

目的：证明系统不会因为预测器本身带来太大开销。

---

## 8.2 Experimental setup

### 8.2.1 Testbed

建议覆盖：

| 平台 | 配置 | 用途 |
|---|---|---|
| Ascend 910A server | 两个独立 NPU full-mesh fabric，每个 fabric 连接 4 个 910A | 验证 910A 适配性 |
| Ascend 910B server | 8 个 910B NPU，Kunpeng 920 CPU，NUMA memory，PCIe/HCCS/RDMA | 主实验平台 |
| Synthetic single-host setup | 可控 memcpy pattern | 模型准确性与 ablation |
| Optional multi-node cluster | 分布式训练/collective | 检测 utility 和 workload impact |

需要记录：

- CPU 型号和核心数；
- 内存容量；
- NUMA 拓扑；
- NPU 数量；
- CANN/driver 版本；
- OS 版本；
- HCCL/MindSpore/PyTorch 版本；
- eBPF 工具链版本。

### 8.2.2 Workloads

建议分为四类。

#### A. Synthetic memcpy workload

用于可控改变 burst-gap pattern。

变量：

- burst length；
- gap length；
- memcpy size distribution；
- path distribution；
- stream 数量；
- async/sync 比例；
- phase drift；
- cross-NUMA ratio。

用途：

- 验证模型预测边界；
- 精确计算 oracle；
- 做 ablation 和 sensitivity。

#### B. Single-node AI workload

例如：

- CNN training；
- Transformer inference；
- recommendation model；
- data loading + H2D copy；
- checkpoint save/load。

关注：

- H2D/D2H memcpy pattern；
- checkpoint burst；
- input pipeline burst；
- iteration phase。

#### C. Multi-NPU collective workload

例如：

- HCCL all-reduce；
- all-to-all；
- reduce-scatter；
- distributed training microbenchmark。

关注：

- NPU interconnect path；
- synchronization-sensitive tail latency；
- probe 对 collective 的影响。

#### D. Mixed workload / interference workload

例如：

- 同时运行训练和 checkpoint；
- 背景 D2D copy；
- cross-NUMA data loading；
- 多进程、多 stream。

关注：

- predictor 在 workload drift 下的表现；
- confidence 是否会自动下降；
- conservative mode 是否有效。

### 8.2.3 Baselines

必须有足够 baseline，否则实验说服力不强。

| Baseline | 含义 | 目的 |
|---|---|---|
| No probing | 不探测 | workload overhead 下界 |
| Fixed probing | 固定周期 probe | 对比传统方法 |
| Random probing | 随机时间 probe | 对比无感知调度 |
| Threshold probing | 当前利用率低于阈值或异常时 probe | 对比 HostDiag-style window selection |
| EWMA-only | 只用 gap EWMA/quantile | 对比主模型收益 |
| Survival-no-calib | survival predictor 无校准 | 证明 calibration 价值 |
| Fixed-window predictor | 固定时间窗输入模型 | 证明 event-driven 表示价值 |
| Oracle gap | 离线知道真实未来 gap | 理论上限 |

### 8.2.4 Metrics

#### Predictor metrics

1. **Safe-window precision**

\[
Precision_{safe}=\frac{N_{predicted\ safe\ and\ actually\ safe}}{N_{predicted\ safe}}
\]

2. **False-safe rate**

\[
FalseSafeRate=\frac{N_{predicted\ safe\ but\ overlapped}}{N_{predicted\ safe}}
\]

这是最重要的预测器指标。

3. **Safe-window recall**

\[
Recall_{safe}=\frac{N_{actual\ safe\ windows\ detected}}{N_{actual\ safe\ windows}}
\]

4. **Gap lower-bound coverage**

\[
Coverage=Pr(G_{actual} \geq \hat{G}^{lower})
\]

例如目标是 95% coverage。

5. **Prediction error**

\[
MAE=|G_{actual}-\hat{G}|
\]

MAE 不是主指标，但可作为辅助。

6. **Calibration error**

Expected Calibration Error, ECE：

\[
ECE=\sum_b \frac{|B_b|}{n}|acc(B_b)-conf(B_b)|
\]

7. **Cold-start cost**

达到稳定 safe precision 所需的时间或样本数。

8. **Drift recovery time**

workload pattern 改变后，预测器恢复到目标 precision 所需时间。

#### Scheduling metrics

1. **Probe-burst overlap ratio**

\[
R_{overlap}=\frac{\sum_i |P_i\cap B|}{\sum_i |P_i|}
\]

2. **Safe probing ratio**

\[
R_{safe}=\frac{N_{probe\ no\ overlap}}{N_{probe}}
\]

3. **Probe opportunity utilization**

\[
Util_{opp}=\frac{N_{safe\ windows\ used}}{N_{safe\ windows\ available}}
\]

4. **Probe cancellation rate**

衡量 late cancellation 是否频繁。

5. **Probe downgrade rate**

衡量 confidence-aware 降级机制是否生效。

#### Workload impact metrics

1. **Iteration slowdown**

\[
Slowdown=\frac{T_{with\ probe}-T_{baseline}}{T_{baseline}}
\]

2. **Tail iteration time**

- p95 iteration time；
- p99 iteration time；
- max iteration time。

3. **Throughput loss**

- samples/sec；
- tokens/sec；
- steps/sec。

4. **Memcpy latency inflation**

业务 memcpy 的平均、p95、p99 latency 增加。

5. **Collective slowdown**

HCCL all-reduce / all-to-all 的 p95/p99 latency。

6. **Checkpoint delay**

checkpoint save/load time 是否被 probe 放大。

#### Detection utility metrics

1. **Fault detection recall**

\[
Recall_{fault}=\frac{DetectedFaults}{InjectedFaults}
\]

2. **False positive rate**

probe 或 analyzer 误报异常的比例。

3. **Detection latency**

\[
Latency_{detect}=T_{first\ detected}-T_{fault\ injected}
\]

4. **Useful probe ratio**

\[
UsefulProbeRatio=\frac{N_{probes\ contributing\ to\ detection}}{N_{all\ probes}}
\]

#### System overhead metrics

- eBPF hook CPU overhead；
- predictor CPU overhead；
- memory usage；
- ring buffer drop rate；
- event processing latency；
- model inference latency；
- probe scheduler latency。

---

## 8.3 Experiment 1: Traffic predictability characterization

### 目的

证明 Ascend memcpy traffic 存在可学习规律。

### 方法

对不同 workload 采集 eBPF trace，离线分析：

- burst duration distribution；
- gap duration distribution；
- inter-arrival distribution；
- per-path gap distribution；
- iteration-aligned pattern；
- autocorrelation；
- phase-specific gap statistics。

### 对比维度

- H2D vs D2H vs D2D；
- 910A fabric 0 vs fabric 1；
- local NUMA vs remote NUMA；
- sync memcpy vs async memcpy；
- steady training vs checkpoint phase；
- single stream vs multi-stream。

### 预期结论

- memcpy traffic 的 gap 分布有明显长尾；
- 同一 workload 内，iteration 对齐后 burst-gap pattern 重复性强；
- 不同 path 的 gap pattern 差异明显，需要 path-aware prediction；
- checkpoint / data loading 会产生明显 phase drift，需要 confidence calibration。

### 图表

- **Figure 8:** 不同 workload 的 burst-gap timeline。
- **Figure 9:** gap duration CDF，标记 latency probe 和 bandwidth probe 所需时长。
- **Figure 10:** iteration-aligned heatmap，展示 burst 出现位置的重复性。
- **Table 3:** 各 workload 的 mean gap、p50、p90、可容纳 probe 的 gap 比例。

---

## 8.4 Experiment 2: Safe-window prediction accuracy

### 目的

验证预测器是否能准确预测高置信度空闲窗口。

### 方法

使用 trace replay 或在线运行，对比不同模型：

- EWMA-only；
- fixed-window predictor；
- raw-event model；
- survival predictor；
- survival + calibration；
- oracle。

### 指标

- false-safe rate；
- safe-window precision；
- safe-window recall；
- gap lower-bound coverage；
- MAE；
- ECE；
- Brier score；
- per-horizon AUC / PR-AUC。

### 关键实验设计

#### 2.1 Multi-horizon accuracy

分别评估：

- 10 µs；
- 25 µs；
- 50 µs；
- 100 µs；
- 250 µs；
- 500 µs；
- 1 ms。

因为不同 probe 类型需要不同时间。不能只报告单一预测误差。

#### 2.2 Confidence calibration

画 reliability diagram：

- x 轴：预测概率；
- y 轴：实际 safe ratio；
- 对比 calibration 前后。

#### 2.3 Lower-bound coverage

验证目标 coverage，例如 95%。

如果预测器输出 \(\hat{G}^{lower}\)，实际 gap 大于该下界的比例应接近或高于目标 coverage。

### 预期结论

- survival predictor 相比 EWMA 和 fixed-window 有更低 false-safe rate；
- calibration 显著降低高置信度窗口的误判；
- lower-bound gap 比 mean gap 更适合调度 probe；
- 长 horizon 预测 recall 会下降，但 precision 应保持高。

### 图表

- **Figure 11:** safe-window precision/recall across horizons。
- **Figure 12:** false-safe rate 对比。
- **Figure 13:** confidence reliability diagram。
- **Figure 14:** gap lower-bound coverage。

---

## 8.5 Experiment 3: Data representation ablation

### 目的

回应数据处理争议：不用固定时间窗，也不直接使用原始事件，而使用 probe-aware event-driven intervalization。

### 方法

对比三种输入表示：

1. **Fixed time window**
   - 例如 50 µs、100 µs、1 ms bin；
   - 特征是窗口内 bytes、event count、utilization。

2. **Raw event sequence**
   - 直接使用最近 K 个原始 memcpy 事件；
   - 不合并 micro-gap。

3. **Probe-aware intervalization**
   - 合并不能容纳 probe 的 micro-gap；
   - 维护 busy-idle interval；
   - 本文方法。

### 指标

- false-safe rate；
- safe precision；
- safe recall；
- model inference cost；
- training/update cost；
- 对 short probe 和 long probe 的表现。

### 预期结论

- 固定窗口会损失窗口边界信息，导致 recall 或 precision 下降；
- raw event 容易将 micro-gap 误认为可用窗口，false-safe rate 较高；
- probe-aware intervalization 在 precision 和 recall 之间取得最好平衡。

### 图表

- **Figure 15:** 三种表示下的 false-safe rate。
- **Figure 16:** 固定窗口大小 sensitivity。
- **Table 4:** 表示方法的准确率与开销对比。

---

## 8.6 Experiment 4: Probe scheduling effectiveness

### 目的

证明预测窗口能真正减少 probe 与业务流量 overlap。

### 方法

在相同 probe budget 下对比：

- fixed probing；
- random probing；
- threshold probing；
- EWMA-only probing；
- FlowGap；
- oracle。

控制变量：

- probe count 相同；
- probe byte volume 相同；
- probe type 相同；
- workload 相同。

### 指标

- overlap ratio；
- safe probing ratio；
- harmful probe count；
- cancellation rate；
- downgrade rate；
- per-path overlap。

### 预期结论

FlowGap 的 probe 数量不一定最少，但 harmful probe 显著减少。

要强调：

> FlowGap is not simply probing less; it shifts probes from busy bursts to predicted idle gaps.

### 图表

- **Figure 17:** probe-burst overlap ratio。
- **Figure 18:** timeline case study，展示 FlowGap 如何避开 burst。
- **Figure 19:** probe type distribution：tiny/latency/bandwidth/downgraded/canceled。

---

## 8.7 Experiment 5: Workload interference

### 目的

证明 FlowGap 降低 probe 对 AI workload 的影响。

### 方法

对每个 workload 运行以下模式：

1. no probing；
2. fixed probing；
3. threshold probing；
4. FlowGap probing；
5. oracle probing。

每组至少重复多次，报告均值和 p95/p99。

### 指标

- average iteration time；
- p95/p99 iteration time；
- throughput loss；
- H2D/D2H/D2D memcpy latency；
- HCCL collective latency；
- checkpoint save/load time；
- NPU utilization；
- CPU overhead。

### 实验场景

#### 5.1 Training workload

观察训练 iteration slowdown。

#### 5.2 Inference workload

观察 request latency 和 tail latency。

#### 5.3 Collective workload

观察 all-reduce / all-to-all tail latency。

#### 5.4 Checkpoint workload

观察 checkpoint save/load 期间 probe 是否加剧 I/O 或 memcpy burst。

### 预期结论

- fixed probing 在 burst-heavy workload 下显著增加 tail latency；
- threshold probing 有改善但仍可能误判短暂 idle；
- FlowGap 接近 oracle，并显著降低 p99 slowdown；
- 对 sync-sensitive workload，FlowGap 的收益更明显。

### 图表

- **Figure 20:** iteration slowdown 对比。
- **Figure 21:** p99 latency / throughput loss 对比。
- **Figure 22:** collective latency CDF。
- **Figure 23:** checkpoint delay 对比。

---

## 8.8 Experiment 6: Detection utility under lower probing interference

### 目的

证明 FlowGap 虽然减少 harmful probe，但没有明显牺牲异常检测能力。

### 方法

注入或模拟主机内异常，比较不同调度策略的 detection recall 和 detection latency。

### Fault / interference scenarios

可以参考 HostDiag 中发现的问题类型，选择与本文相关的子集：

| 类别 | 场景 | 注入方式 | 关注指标 |
|---|---|---|---|
| NPU PCIe BW decrease | NPU 与 host memory 路径带宽下降 | 限速、后台 copy、配置降速或 synthetic throttling | bandwidth probe 是否发现 |
| Memory channel contention | host memory channel 被占用 | background memory benchmark | 是否误判为链路异常，检测时延 |
| CPU interconnect contention | cross-NUMA transfer 受影响 | remote NUMA load | cross-NUMA path probe |
| NPU interconnect disabled/degraded | HCCS 不可用或性能下降 | 配置/模拟 fallback | D2D probe |
| Cross-NUMA data loading | 数据加载绑定错误 | remote NUMA allocation | predictor 是否识别 path pattern 变化 |
| Frequent checkpoint saving | 周期性 D2H/H2D burst | 增加 checkpoint 频率 | 是否误触发 probe 或造成干扰 |
| Small batch / many small flows | 大量小 memcpy | 调整 batch size | short horizon prediction |
| Workload drift | phase pattern 突变 | 切换 workload 或 batch size | confidence 是否下降 |

### 对比方法

- fixed probing；
- threshold probing；
- FlowGap；
- FlowGap with failure-aware fallback；
- oracle。

### 指标

- fault detection recall；
- detection latency；
- false positive rate；
- confirmation probe count；
- useful probe ratio；
- workload slowdown during detection。

### 关键点

需要强调 FlowGap 不是一味减少 probe。它可以在风险升高时进入 failure-aware mode：

- 降低 safe confidence threshold；
- 只发 tiny/confirmation probe；
- 增加 probe priority；
- 但仍控制 probe budget。

### 预期结论

- FlowGap 的 detection recall 接近 fixed/threshold probing；
- detection latency 略有增加但可接受；
- workload slowdown 显著更低；
- useful probe ratio 更高。

### 图表

- **Figure 24:** detection recall vs workload slowdown。
- **Figure 25:** detection latency CDF。
- **Figure 26:** useful probe ratio。
- **Table 5:** 不同 fault scenario 下的检测结果。

---

## 8.9 Experiment 7: Robustness to async uncertainty, event loss, and drift

### 目的

证明预测器在实际部署中可靠。

### 子实验

#### 7.1 Async uncertainty

控制 async completion 可见性：

- sync memcpy only；
- async with stream sync；
- async without timely sync；
- high stream concurrency。

指标：

- false-safe rate；
- safe recall；
- async margin 变化；
- conservative timeline vs estimated timeline 的差异。

#### 7.2 eBPF event loss

人为制造 ring buffer pressure 或采样 drop。

指标：

- data quality confidence 是否下降；
- false-safe rate 是否仍被控制；
- probe 数是否自动减少。

#### 7.3 Workload drift

切换：

- batch size；
- sequence length；
- checkpoint frequency；
- data loading mode；
- single workload → mixed workload。

指标：

- drift detection delay；
- drift recovery time；
- conservative mode duration；
- high-confidence prediction 暂停是否有效。

### 预期结论

- 数据质量下降时，FlowGap 通过 confidence 降级而不是盲目 probe；
- workload drift 发生时，短暂降低 recall，但保持低 false-safe rate；
- async uncertainty 主要影响 recall，而不是 precision。

### 图表

- **Figure 27:** event loss rate vs confidence / false-safe rate。
- **Figure 28:** workload drift 后的 confidence 和 precision 变化。
- **Figure 29:** async workload 下 conservative timeline 与 estimated timeline 的 safe window 数量对比。

---

## 8.10 Experiment 8: System overhead

### 目的

证明 eBPF 采集、预测器和调度器的开销低。

### 方法

测量：

- eBPF hook 单次事件开销；
- event processing throughput；
- predictor inference latency；
- CPU usage；
- memory usage；
- ring buffer drop rate；
- 对 workload 的 baseline overhead。

### 对比

- FlowGap disabled；
- only eBPF monitor enabled；
- monitor + predictor；
- monitor + predictor + prober；
- worst-case continuous predictor/prober。

### 指标

- CPU core usage；
- memory MB；
- average event processing latency；
- p99 event processing latency；
- end-to-end safe-window publication latency；
- workload slowdown caused by monitoring only。

### 预期结论

- 预测器长期运行开销应接近 monitor 级别；
- prober 按需运行，平均开销低；
- 相比固定探测，FlowGap 总 probe byte volume 和 harmful overlap 更低。

### 图表

- **Figure 30:** CPU/memory overhead time series。
- **Figure 31:** event rate vs processing latency。
- **Table 6:** 各模块开销。

---

## 8.11 Sensitivity analysis

### 参数

需要评估以下参数：

| 参数 | 含义 | 预期影响 |
|---|---|---|
| history length K | 最近多少 gap/burst 参与预测 | K 太小不稳定，太大适应慢 |
| confidence threshold \(\eta\) | 允许 probe 的置信度阈值 | 越高 false-safe 越低，recall 越低 |
| safety margin M | 安全裕量 | 越大越保守 |
| micro-gap merge threshold | 合并 micro-gap 的阈值 | 影响 safe-window precision/recall |
| horizon set H | 预测时间尺度 | 影响不同 probe 类型 |
| async margin | async 执行不确定性 | 影响 async workload recall |
| calibration window | 校准历史长度 | 影响稳定性和响应速度 |
| drift threshold | 漂移检测敏感度 | 影响恢复速度和误保守 |
| probe size | 探测大小 | 影响窗口需求和干扰 |
| probe budget α | probe 可占用 idle capacity 比例 | 影响 detection utility 和干扰 |

### 图表

- **Figure 32:** confidence threshold vs false-safe rate / recall。
- **Figure 33:** safety margin vs workload slowdown / probe count。
- **Figure 34:** history length vs prediction accuracy。
- **Figure 35:** probe size vs safe-window availability。

---

## 8.12 Evaluation summary table

建议最后用一张表总结每个实验回答什么问题。

| 实验 | 回答的问题 | 主要指标 | 主要图表 |
|---|---|---|---|
| Traffic characterization | gap 是否可预测 | gap CDF, autocorrelation | Fig. 8–10 |
| Prediction accuracy | 预测器准不准 | false-safe, precision, ECE | Fig. 11–14 |
| Representation ablation | 数据表示是否合理 | false-safe, recall, overhead | Fig. 15–16 |
| Scheduling effectiveness | 是否减少 overlap | overlap ratio, safe probing ratio | Fig. 17–19 |
| Workload impact | 是否降低干扰 | slowdown, p99, throughput | Fig. 20–23 |
| Detection utility | 是否漏检故障 | recall, latency, FPR | Fig. 24–26 |
| Robustness | 是否能处理不确定性 | drift recovery, event loss impact | Fig. 27–29 |
| Overhead | 是否可部署 | CPU, memory, processing latency | Fig. 30–31 |
| Sensitivity | 参数是否稳定 | precision/recall/slowdown | Fig. 32–35 |

---

# 9. Related Work

建议短写，分三类。

## 9.1 Intra-host diagnosis

- Hostping；
- HostDiag；
- RDMA/RNIC bottleneck diagnosis；
- server-side bottleneck monitoring。

强调区别：本文不提出一个完整诊断系统，而是解决主动探测时机选择问题。

## 9.2 Active probing

- fixed probing；
- random probing；
- threshold-triggered probing；
- service-aware probing。

强调区别：本文将 probing 从周期性任务转化为 safe-window prediction。

## 9.3 AI accelerator monitoring

- profiler；
- runtime trace；
- hardware counters；
- eBPF-based monitoring。

强调区别：本文使用低侵入事件流预测 probe opportunity，而不是做完整性能剖析。

---

# 10. Conclusion

总结三点：

1. Ascend memcpy traffic 具有可学习的 burst-gap 模式；
2. FlowGap 使用 eBPF 事件流和置信度校准模型预测 safe probing window；
3. 实验表明 FlowGap 能减少 probe-burst overlap、降低 AI workload slowdown，同时保持接近传统探测的异常检测能力。

---

# 11. 建议的论文图表清单

| 编号 | 图/表 | 内容 |
|---|---|---|
| Figure 1 | Motivation | probe overlap 导致 slowdown |
| Figure 2 | Topology | Ascend 910A/910B path/link |
| Figure 3 | Trace | 不同 workload 的 burst-gap |
| Figure 4 | Fixed vs gap-aware | 探测干扰对比 |
| Figure 5 | Architecture | Predictor-Prober-Analyzer |
| Figure 6 | Event pipeline | eBPF → timeline → prediction |
| Figure 7 | Safe-window example | 预测窗口与 probe placement |
| Figure 8 | Traffic characterization | burst-gap timeline |
| Figure 9 | Gap CDF | gap 可容纳 probe 的比例 |
| Figure 10 | Iteration heatmap | phase-dependent pattern |
| Figure 11 | Prediction accuracy | horizon-wise precision/recall |
| Figure 12 | False-safe rate | 模型对比 |
| Figure 13 | Calibration | reliability diagram |
| Figure 14 | Lower-bound coverage | 保守预测覆盖率 |
| Figure 15 | Representation ablation | raw/window/interval 对比 |
| Figure 16 | Window sensitivity | 固定窗口大小影响 |
| Figure 17 | Overlap ratio | 调度效果 |
| Figure 18 | Case timeline | FlowGap 避开 burst |
| Figure 19 | Probe decisions | normal/downgrade/cancel |
| Figure 20 | Training slowdown | workload impact |
| Figure 21 | Tail latency | p95/p99 对比 |
| Figure 22 | Collective CDF | HCCL latency |
| Figure 23 | Checkpoint delay | checkpoint 影响 |
| Figure 24 | Detection tradeoff | recall vs slowdown |
| Figure 25 | Detection latency | CDF |
| Figure 26 | Useful probe ratio | 探测有效性 |
| Figure 27 | Event loss | 数据质量影响 |
| Figure 28 | Drift recovery | workload drift |
| Figure 29 | Async uncertainty | async timeline 对比 |
| Figure 30 | Overhead timeline | CPU/mem |
| Figure 31 | Processing latency | event rate vs latency |
| Figure 32–35 | Sensitivity | 参数敏感性 |
| Table 1 | Symbols | 主要符号 |
| Table 2 | Testbed | 平台配置 |
| Table 3 | Workloads | workload 列表 |
| Table 4 | Baselines | 对比方法 |
| Table 5 | Fault scenarios | 故障/干扰注入 |
| Table 6 | Module overhead | 实现开销 |

---

# 12. 写作时需要反复强调的点

1. **不是少 probe，而是减少 harmful probe。**

   FlowGap 的目标不是简单降低探测频率，而是把 probe 从 memcpy burst 中移到高置信度 gap 中。

2. **不追求精确重建全量流量。**

   预测器只需要保守判断未来 horizon 内是否足够空闲。

3. **false-safe rate 比 MAE 更重要。**

   论文中应将 false-safe rate、安全窗口 precision、lower-bound coverage 作为预测器核心指标。

4. **实验必须包含 detection utility。**

   否则 reviewer 会认为低干扰只是因为 probe 变少。必须证明故障检测能力没有明显下降。

5. **置信度校准是关键创新点之一。**

   仅有预测模型不足以支撑系统可靠性。必须说明如何根据历史命中率、数据质量和 workload drift 调整 confidence。

6. **910A/910B 适配性要体现在 path/link/phase 特征中。**

   不要只说“支持 Ascend”，而要体现 NUMA、NPU fabric、HCCS、stream、async memcpy 对预测器设计的影响。

