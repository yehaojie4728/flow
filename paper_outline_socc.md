# FlowGap — SoCC 2026 论文大纲（12 页正文）

> **Title**: FlowGap: Predictive Safe-Window Probing for Low-Interference Monitoring of AI Accelerator Servers
> **Venue**: ACM SoCC 2026 · Research Full · `\documentclass[sigconf,review,anonymous]{acmart}`
> **Budget**: 12 页正文 + 不限参考文献 · 9pt · 双盲

---

## 篇幅分配总览（12 页）

| 章节 | 页数 | 配图/表 |
|------|:----:|---------|
| Abstract | 0.25 | — |
| 1. Introduction | 1.5 | Fig 1（动机图） |
| 2. Background & Motivation | 1.75 | Fig 2（gap 结构）、Fig 3（方向不对称） |
| 3. System Design | 3.0 | Fig 4（架构图）、Alg 1–3、Table 1（特征表） |
| 4. Implementation | 0.75 | — |
| 5. Evaluation | 3.5 | Fig 5–11、Table 2–4 |
| 6. Discussion | 0.5 | — |
| 7. Related Work | 0.75 | — |
| 8. Conclusion | 0.25 | — |
| References | 不限 | — |
| **合计正文** | **~12.25** | （压缩到 12 页） |

---

## Abstract（约 200 词，0.25 页）

四句式结构：

1. **问题**：AI 加速器服务器（如 Ascend NPU 集群）的链路健康监控需要主动探测，但盲目探测会与训练流量竞争带宽、放大 collective 通信尾延迟。
2. **洞察**：NPU 的 `aclrtMemcpy` 流量呈 burst-gap 结构，gap 在短时间尺度内可学习、可预测。
3. **方法**：FlowGap 用 eBPF 非侵入采集 memcpy 事件，提取 30 维特征，用多 horizon GBDT 预测安全窗口，仅在高置信度窗口触发探针。
4. **结果**：在 Ascend 910A × 8 真实训练（GLM-6B）和推理（Qwen2-7B）负载上，预测 precision 0.96–1.00、假安全率 <2%、在线探针开销 0.064%、eBPF CPU 开销中位数 +0.075pp，且为唯一实现零干扰（Unsafe%=0%）+ 高路径覆盖的非 Oracle 调度策略。

---

## 1. Introduction（1.5 页）

### ¶1 — 大背景
AI 训练/推理集群规模化，加速器服务器内部互联（HCCS/NVLink/PCIe）成为性能瓶颈与故障源。引用：单个 intra-host 瓶颈可拖垮整个分布式训练 [Hostping NSDI'23]。

### ¶2 — 监控的必要性与矛盾
持续链路健康监控需要主动探测（latency/bandwidth probe）。但探测本身消耗与训练相同的传输通道 → 形成"监控-干扰"两难：要看清链路必须发探针，发探针又会干扰被监控的训练任务。

### ¶3 — 现有方案的不足（三类）
- 固定周期探测（Pingmesh 类）：盲探，与 burst 重叠不可控；
- 阈值/异常触发（HostDiag 类）：只判断"当前"忙闲，无法预测"未来"是否安全；
- 被动监控（µMon 类）：看得到流量但无法主动测链路健康。
**共性缺陷**：都没有回答"何时探测才不干扰业务"。

### ¶4 — 核心洞察
用真实 trace 引出：Ascend memcpy 流量虽 bursty，但 gap 的时间统计在迭代间高度稳定（D2H gap p50 在 Pass1/Pass2 仅差 ~5µs）。因此无需精确重建全部流量，只需**保守预测未来一段窗口是否足够空闲**。把探测从"周期/阈值触发"转化为"置信度门控的安全窗口探测"。

### ¶5 — FlowGap 概述
一句话串起三模块：eBPF Tracer → 30维特征 + 多horizon GBDT 预测器 → 置信度门控调度器（独立 stream 执行探针）。强调离线训练 + 在线调度两阶段。

### ¶6 — 贡献清单（三点）
1. **问题形式化**：将加速器服务器探测时机选择建模为多 horizon 安全窗口预测，并定义对应 3 类探针（TINY/NORMAL/BW）的 8 个 horizon。
2. **系统设计**：FlowGap，一个 eBPF + 轻量 GBDT 的预测式探测系统，可解释、冷启动友好、推理 <1ms。
3. **真机评估**：Ascend 910A × 8 上跨训练/推理负载验证，给出预测精度、调度收益、系统开销和故障检测的端到端证据。

### ¶7 — 结果与路线图预览
一句话点出关键数字（precision 0.96+、FSR <2%、开销 0.064%），并给出本文章节结构。

**Fig 1（动机图，P0 待绘）**：同一段真实 memcpy trace 上叠加 fixed probing（与 burst 重叠，红）与 FlowGap probing（落在 gap 中，绿）；右侧小柱状图示意 Unsafe% 对比（fixed/threshold vs FlowGap）。

---

## 2. Background & Motivation（1.75 页）

### 2.1 Ascend NPU 服务器内部通信（0.4 页）
- 8× NPU + HCCS 全互联 + 跨 NUMA 拓扑；
- 传输路径：Host DDR↔NPU HBM（H2D/D2H）、NPU↔NPU（D2D）；
- `aclrtMemcpy`（同步）/ `aclrtMemcpyAsync`（异步）/ `aclrtSynchronizeStream`；
- 强调：探针与训练共享这些物理通道 → 干扰来源。

### 2.2 eBPF 事件可见性（0.35 页）
- uprobe 插桩 `libascendcl.so`，可获取 src/dst/size/start/end/direction/thread-device binding；
- 非侵入，不依赖训练框架改动；
- 与 HostDiag 对比：HostDiag 用 eBPF 做阈值触发（reactive），FlowGap 用同样的可见性做预测（predictive）。

### 2.3 关键观察（用实测数据，0.7 页）
基于 GLM-6B 完整 trace（Pass1 170,556 events/5994s；Pass2 171,376 events/6014s）：

- **Obs 1 — gap 高度结构化**：D2H 路径 gap p50 = 186–200µs、p90 ≈ 18ms；Tiny-safe(≥50µs)=100%，BW-safe(≥5.1ms)≈30%。
- **Obs 2 — 跨迭代稳定**：Pass1 与 Pass2 的 per-path gap 分布几乎一致（支撑可预测性，也是后续跨 pass 验证的基础）。
- **Obs 3 — 方向不对称**：D2H gap 短而密（p50≈190µs），H2D gap 长而稀（p50 500–800µs）。→ 说明为何要 per-path、per-direction 预测。

**Fig 2**：Pass1 vs Pass2 per-path gap p50/p90 箱线/小提琴图。
**Fig 3**：H2D vs D2H gap 分布对比（CDF 或直方图）。

### 2.4 为什么预测可行且必要（0.3 页）
- 可行：gap 跨迭代稳定 + 局部窗口含足够信息（前瞻消融 §5）；
- 必要：盲探/阈值探测的 Unsafe% 高达 44–70%（前瞻 §5.4 P0.1）；
- 收敛到本文的问题陈述：给定最近 W 个事件，预测某 path 在未来 horizon h 内保持空闲的概率，并据此门控探针。

---

## 3. System Design（3.0 页）

### 3.1 Overview（0.4 页）
两阶段流水线图 + 数据流叙述。离线：trace→特征→训练 8 个 horizon 的 GBDT。在线：tail eBPF→特征→预测→门控→执行→反馈。
**Fig 4**：系统架构图（已有 `flowgap_architecture.png`）。

### 3.2 问题形式化（0.3 页）
- 定义 path、busy interval、gap interval；
- 安全窗口标签：对 horizon h，`y = 1[gap_duration ≥ h]`；
- 目标：最小化 False-Safe Rate（预测安全但实际不安全），同时保持探测覆盖；
- 多 horizon ↔ 3 类探针映射（TINY 50µs / NORMAL 500µs / BW 5.1ms）。

### 3.3 eBPF Tracer（0.4 页）
- uprobe 入口/返回挂载 `aclrtMemcpy`；`BPF_HASH(thread_device)` 跟踪每线程设备绑定；
- `BPF_PERF_OUTPUT` 异步推送，`--min-size` 过滤；NUMA 感知。
- 输出 schema（单事件 + 聚合窗口）。

### 3.4 Trace Parser & Intervalization（0.3 页）
- `FlowEvent` → `group_by_path` → `build_timeline` 得到 busy/gap 双时间线；
- 重叠合并处理并发传输；38 单元测试。
- **Algorithm 引用**：与特征提取衔接。

### 3.5 Feature Extraction（0.5 页）
- 滑动窗口 WIN=50；30 维，分 9 组。
- **Table 1**：特征组 × 维度 × 含义（gap_stats 7 / burst_stats 5 / idle_age 4 / path_identity 5 / resource 5 / time 4 …）。
- 前瞻一句：消融显示 gap_stats 为关键组（§5.2）。
- **Algorithm 2**：Feature Extraction（30-dim）。

### 3.6 Multi-Horizon GBDT Predictor（0.5 页）
- 为何 GBDT 而非 DNN：小样本（16K）抗过拟合、可解释、CPU 推理 <1ms、易校准；
- 8 个独立二分类器，每 horizon 一个；超参表（n_estimators, depth=4, lr=0.1, subsample=0.8）；
- 概率输出 + 校准（前瞻 ECE，§5）。
- **Algorithm 3**：GBDT Offline Training。

### 3.7 Confidence-Gated Scheduler（0.4 页）
- 在线循环：预测 8 horizon → 对 P(safe)>η 选最长可行探针 → urgency 排序 → budget B 约束；
- 7 种策略框架（本文 + 5 baseline + oracle）作为评估锚点；
- 置信度阈值 η 的作用（前瞻敏感性 §5.5）。
- **Algorithm 1**：Online Predictive Probe Scheduling。

### 3.8 Probe Executor（0.2 页）
- AscendCL ctypes，**独立 stream 隔离**；
- TINY latency probe（1KB）/ BW probe（128–256MB）；超时主动 cancel（`aclrtSynchronizeStream`）。

---

## 4. Implementation（0.75 页）

### ¶1 — 代码与栈
Python bpfcc（eBPF）+ scikit-learn（GBDT）+ AscendCL ctypes（执行），不依赖 MindSpore/PyTorch；模块行数/测试覆盖（38 parser 单测、9 NPU 真机测试）。

### ¶2 — 部署环境
Ascend 910A（aarch64, 192 核）、CANN 8.0.RC3、EulerOS 2.0 SP10、MindSpore 2.2.14、MindIE 1.0.T65。

### ¶3 — 工程要点
线程-设备绑定解决多 NPU 并发；异步 memcpy 的保守边界估计；模型持久化（879KB pkl，8 horizon）。

---

## 5. Evaluation（3.5 页）

### 5.0 实验设置（0.4 页）
- 硬件/软件/负载表（GLM-6B 训练 341,934 events/Pass；Qwen2-7B 推理 162 样本）；
- 指标定义：Precision / Recall / **FSR（关键安全指标）** / Brier / Overhead% / Unsafe% / BW% / Paths / Detection Latency；
- **RQ 列表**：
  - RQ1：gap 是否可预测？（§5.1–5.3）
  - RQ2：能否跨负载泛化？（§5.4 错→重排，见下）
  - RQ3：预测能否转化为更好的调度与可接受的开销？（§5.5–5.7）

> 章节顺序建议：5.1 预测精度 → 5.2 消融 → 5.3 冷启动/drift/oracle → 5.4 跨负载 → 5.5 策略对比 → 5.6 开销 → 5.7 故障检测。

### 5.1 RQ1 预测精度（跨 Pass 验证，0.5 页）
- **Table 2**：Pass1→Pass2，3 horizon。
  | Horizon | Precision | Recall | FSR | Brier |
  |---|---|---|---|---|
  | 50µs (TINY) | 1.0000 | 1.0000 | 0.0000 | 0.0000 |
  | 500µs (NORMAL) | 0.9647 | 0.9608 | 0.0150 | 0.0172 |
  | 5.1ms (BW) | 0.9636 | 0.9425 | 0.0123 | 0.0177 |
- 论点：TINY 完美预测（gap p50 远超 50µs）；NORMAL/BW 也达 0.96 precision、FSR <2%；训练 25.7s。

### 5.2 特征消融（0.4 页）
- Leave-One-Group-Out，**Fig 5**（已有 `p1.1_feature_ablation.png`）。
- 论点：仅 gap_stats 关键（precision −~4pp），其余 8 组 ≈0 → "简单即可"的设计哲学；并诚实讨论冗余/实验设计的解释（见 §6）。

### 5.3 冷启动 / Drift / Oracle 上界（0.5 页）
- **冷启动**（Fig 6 / `p2.1_cold_start.png`）：10 样本→0.85，200 样本→0.96+，500→0.98+。论点：20 秒即可冷启动。
- **Drift**（Fig 7 / `p2.2_drift.png`）：后20% precision **优于**前80%（ΔP +0.01~+0.03），无退化。
- **Oracle gap**（Fig 8 / `p2.3_oracle_gap.png`）：η=0.95 时 safe ratio = 1.0000 = Oracle，仅探测次数少 15.7%。论点：FlowGap 接近理论上界。

### 5.4 RQ2 跨负载泛化（0.4 页）
- **Table 3**：GLM-6B 训练 → Qwen2-7B 推理，5-fold CV。
  | Horizon | Precision | Recall | FSR | Brier |
  |---|---|---|---|---|
  | 500µs | 0.975 | 1.000 | 0.0545 | 0.0184 |
  | 5.1ms | 0.951 | 0.952 | 0.0500 | 0.0365 |
- **Fig 9**（`p1.2_second_workload.png`）。论点：训练→推理迁移有效；坦诚 162 样本的局限。

### 5.5 RQ3-a 策略对比（核心实验，0.6 页）
- **Table 4**：7 策略 v2 覆盖度（GLM-6B Pass2, 171,869 events, 163,475 gaps, 6,007s）。
  | 策略 | Probes | BW% | Overhead% | Unsafe% | Paths |
  |---|---|---|---|---|---|
  | no_probing | 0 | 0% | 0% | 0% | 0 |
  | fixed_interval | 2,405 | 0% | 0.002% | 0% | 36 |
  | random | 1,614 | 32.8% | 0.050% | 45.8% | 22 |
  | threshold | 163,475 | 34.0% | 5.611% | 70.4% | 45 |
  | ewma_only | 102,668 | 55.8% | 5.195% | 43.9% | 24 |
  | **flowgap** | 163,206 | 23.2% | 3.346% | **0.0%** | 25 |
  | oracle | 163,475 | 29.6% | 4.258% | 0% | 45 |
- **Fig 10**（`fig1_policy_comparison.pdf`）。论点：flowgap 是唯一同时 Unsafe%=0% + 含 BW 探针 + 多路径覆盖的非 Oracle 策略；threshold/ewma 干扰率 44–70%。

### 5.6 RQ3-b 系统开销（0.5 页）
- **在线探针开销（P0.3）**：1200s 训练 488 探针 / 0.772s / **0.064%**。
- **eBPF 开销（P1.3）**：系统 CPU 中位数 +0.075pp、均值 +1.17pp、tracer 进程 0.002%。
- **校准（P0.2.2）**：**Fig 11**（`fig2_calibration.pdf`）reliability curve + ECE<0.02。
- **Fig（overhead breakdown）**：`fig3_overhead_breakdown.pdf`。
- 论点：开销可忽略，概率可信。

### 5.7 RQ3-c 故障检测（0.2 页）
- 注入带宽竞争，基线 20.10 GB/s，阈值 14.07 GB/s。
- 结果：**检测延迟 14.65s**；recall 49.2%、precision 47.5%。
- 论点：能检出（带宽 20.1→10.77 GB/s），但 recall/precision 受限于训练带宽稀疏 + 注入错峰；坦诚列为局限并给出改进路径（§6）。

### 5.8 敏感性（置信度阈值 η，0.3 页）
- η sweep：0.50→0.70 precision 0.9545→0.9983、BW probes −12.6%；η≥0.95 探针为 0（过保守）。
- 论点：推荐 η=0.70 平衡 precision 与覆盖。（可作小表或并入 5.6）

---

## 6. Discussion（0.5 页）

### ¶1 — 设计取舍
gap_stats 主导说明问题本质是时序统计；简单模型够用，复杂特征边际收益低（也需警惕消融设计局限）。

### ¶2 — 局限
1. 单负载族 + Qwen2 仅 162 样本；
2. 故障检测 recall/precision 偏低（带宽稀疏 + 注入错峰）；
3. 单节点评估；
4. 8 组特征消融为 0 的多重可能解释（冗余 / 负载相关 / leave-one-out 互补）。

### ¶3 — 未来工作
故障注入参数加强、在线 drift+增量训练、多节点联合调度、"何时探测"+"在哪探测"联合优化、更多模型/并行策略。

---

## 7. Related Work（0.75 页，4 子主题各 1 段）

### 7.1 Intra-host monitoring & diagnosis
Hostping [NSDI'23]、HostDiag。差异：FlowGap 回答"何时安全探测"。

### 7.2 Active probing in datacenter networks
Pingmesh [SIGCOMM'15] / Pingmesh 2.0、RD-Probe（空间覆盖）、µMon（被动 µs 监控）。差异：FlowGap 关注**时间覆盖**。

### 7.3 AI infrastructure monitoring
PerfTracker（事后诊断）、HPN / Meta RoCE（架构）、Spectrum-X（硬件）。差异：FlowGap 是运行时**预防性**监控。

### 7.4 ML for network measurement
传统流量预测（分钟级）/异常检测。差异：FlowGap 首个用 GBDT 预测**µs 级 gap** 做探测调度。

---

## 8. Conclusion（0.25 页）
重申"监控-干扰"两难 → burst-gap 可预测洞察 → eBPF+GBDT 预测式探测 → 真机零干扰高覆盖 + 开销可忽略；展望多节点与在线自适应。

---

## 配图/表索引（投稿用）

| 编号 | 内容 | 资产状态 |
|:---:|------|---------|
| Fig 1 | 动机图（fixed vs FlowGap） | **待绘（P0）** |
| Fig 2 | Pass1/Pass2 per-path gap 分布 | 待绘（数据已有） |
| Fig 3 | H2D vs D2H gap 分布 | 待绘（数据已有） |
| Fig 4 | 系统架构 | 已有 `flowgap_architecture.png` |
| Fig 5 | 特征消融 | 已有 `p1.1_feature_ablation.png` |
| Fig 6 | 冷启动 | 已有 `p2.1_cold_start.png` |
| Fig 7 | Drift | 已有 `p2.2_drift.png` |
| Fig 8 | Oracle gap | 已有 `p2.3_oracle_gap.png` |
| Fig 9 | 跨负载 | 已有 `p1.2_second_workload.png` |
| Fig 10 | 策略对比 | 已有 `fig1_policy_comparison.pdf` |
| Fig 11 | 校准曲线 | 已有 `fig2_calibration.pdf` |
| Fig（overhead） | 开销分解 | 已有 `fig3_overhead_breakdown.pdf` |
| Table 1 | 30 维特征表 | 数据已有 |
| Table 2 | 跨 Pass 预测精度 | 数据已有 |
| Table 3 | 跨负载泛化 | 数据已有 |
| Table 4 | 7 策略对比 | 数据已有 |
| Alg 1–3 | 三个算法 | 已有 `algorithms.tex` |

> 注：当前可用配图/表已覆盖除 Fig 1–3 外的全部需求；Fig 1 是投稿前必须补的动机图。
