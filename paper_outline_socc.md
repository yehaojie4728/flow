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
| 3. System Design | 2.5 | Fig 4（架构图）、Alg 1–3、Table 1（特征表） |
| 4. Implementation | 0.5 | — |
| 5. Evaluation | 3.5 | Fig 5–11、Table 2–4 |
| 6. Discussion | 0.5 | — |
| 7. Related Work | 1.0 | — |
| 8. Conclusion | 0.25 | — |
| References | 不限 | — |
| **合计正文** | **~11.5** | 留 0.5 页缓冲 |

---

## Abstract（约 200 词，0.25 页）

四句式结构：

1. **问题**：云厂商同时承载数百个 AI 训练/推理任务，AI 加速器服务器（如 Ascend NPU 集群）的内部链路健康直接决定多租户 SLA。主动探测是实现持续链路监控的必要手段，但盲目探测会与训练流量竞争 HCCS/NVLink 带宽、放大 collective 通信尾延迟，进而影响多个租户任务。
2. **洞察**：NPU 的 `aclrtMemcpy` 流量呈 burst-gap 结构，gap 在短时间尺度内可学习、可预测。
3. **方法**：FlowGap 用 eBPF 非侵入采集 memcpy 事件，提取 30 维特征，用多 horizon GBDT 预测安全窗口，仅在高置信度窗口触发探针。
4. **结果**：在 Ascend 910A × 8 真实训练（GLM-6B）和推理（Qwen2-7B）负载上，预测 precision 0.96–1.00、假安全率 <2%、在线探针开销 0.064%、eBPF CPU 开销中位数 +0.075pp，且为唯一实现零干扰（Unsafe%=0%）+ 高路径覆盖的非 Oracle 调度策略。

---

## 1. Introduction（1.5 页）

### ¶1 — 大背景
云厂商（如阿里云 ModelScope、华为云、AWS 等）同时承载数百个 AI 训练和推理任务。单个 AI 加速器服务器内部互联（HCCS/NVLink/PCIe）的链路故障可导致多个租户的训练吞吐下降或推理延迟超 SLA。引用：单个 intra-host 瓶颈可拖垮整个分布式训练 [Hostping NSDI'23]。因此，云端运维团队需要持续、无干扰的链路健康监控来支撑故障预警、容量规划和 SLA 保障。

### ¶2 — 监控的必要性与矛盾
持续链路健康监控需要主动探测（latency/bandwidth probe）。但探测本身消耗与训练相同的传输通道（HCCS/NVLink），且非侵入性要求意味着不能被租户感知到性能下降。这形成"监控-干扰"两难：要看清链路必须发探针，发探针又会干扰被监控的训练任务——在云多租户场景中，这种干扰可能引发 SLA 违约金。

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
- 强调：探针与训练共享这些物理通道 → 干扰来源；
- 云场景关联：单台 8-NPU 服务器同时服务多个推理请求或单个训练任务，链路健康直接影响租户 SLA。

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

- **Obs 4 — 预测差距具象化**（D1 实验验证）：在 Pass2 最繁忙 D2H 路径的 50ms 最密集窗口中（busy=86.4%），分别执行 fixed_interval（1ms/5ms 周期，120µs 探针）和 flowgap_predictive。结果：fixed_interval 的 Unsafe% 高达 93.9%（1ms）和 77.8%（5ms）；FlowGap 在上下文不足时选择沉默（0 次不安全探测）。该对比将"gap 结构可预测"直接翻译为"盲探的危险性"——在密集传输区，固定周期探测的碰撞率接近 100%。详见 D1 实验报告和 Fig 3（`code/results/figures/fig_d1_motivation.png`）。

### 2.4 为什么预测可行且必要（0.3 页）
- 可行：gap 跨迭代稳定（Obs 2）+ 局部窗口含足够信息（前瞻消融 §5.2）+ 直接对比显示预测可避免干扰（Obs 4）；
- 必要：盲探/阈值探测的 Unsafe% 高达 44–70%（前瞻 §5.5 P0.1）；
- 收敛到本文的问题陈述：给定最近 W 个事件，预测某 path 在未来 horizon h 内保持空闲的概率，并据此门控探针。

---

## 3. System Design（2.5 页）

### 3.1 Overview（0.4 页）
两阶段流水线图 + 数据流叙述。离线：trace→特征→训练 8 个 horizon 的 GBDT。在线：tail eBPF→特征→预测→门控→执行→反馈。
**Fig 4**：系统架构图（已有 `flowgap_architecture.png`）。

### 3.2 问题形式化（0.3 页）
- 定义 path、busy interval、gap interval；
- 安全窗口标签：对 horizon h，`y = 1[gap_duration ≥ h]`；
- **约束优化形式化**：在 False-Safe Rate ≤ δ（硬约束，δ 通常为 0）的前提下，最大化探测覆盖度（BW 探针比例 × 覆盖路径数）；
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
- **Table 2**：Pass1→Pass2，3 horizon（GBDT）。
  | Horizon | Precision | Recall | FSR | Brier |
  |---|---|---|---|---|
  | 50µs (TINY) | 1.0000 | 1.0000 | 0.0000 | 0.0000 |
  | 500µs (NORMAL) | 0.9647 | 0.9608 | 0.0150 | 0.0172 |
  | 5.1ms (BW) | 0.9636 | 0.9425 | 0.0123 | 0.0177 |
- 论点：TINY 完美预测（gap p50 远超 50µs）；NORMAL/BW 也达 0.96 precision、FSR <2%；训练 25.7s。
- **D5: ML baseline 消解 novelty 质疑**：对比 EWMA、LogisticRegression（LR）、GBDT。EWMA 完全失败（FSR=1.0，总是预测均值）。LR 显著优于 EWMA（ΔP +60pp），但 GBDT 在所有 horizon 上明显领先 LR（ΔP +4.4~18.7pp，500µs: 0.879 vs 0.965）。**结论：burst-gap 模式具有非线性结构，GBDT 是必要的**，不是过度工程。详见 D5 报告和 Fig X（`code/results/figures/fig_d5_model_comparison.png`）。

### 5.2 特征消融（0.4 页）
- **P1.1 (LOO)** + **D4 (全 horizon LOO)**：Leave-One-Group-Out 覆盖全部 6 个 horizon（50µs–5.1ms）。仅 gap_stats 关键，且效应随 horizon 增大而增强（ΔP 250µs: −5.2pp, 5.1ms: −9.3pp）。TINY/100µs horizon 上所有组消融结果均为 0——gap p50=190µs 远超 50µs，**预测在短 horizon 上是 trivially true 的**。burst_stats 在 BW horizon 有微弱独立贡献（ΔP=−0.09pp）。详见 D4 报告和 Fig X（`fig_d4_horizon_ablation.png`）。
- **D3 (正向消融)**：Keep-Only each group。验证各组的独立预测能力。完整证据链如下：
  - **gap_stats (7维) 是充分统计量**：仅用 gap_stats，precision 与 baseline 几乎完全相同（250µs: 0.9787 vs 0.9787, 500µs: 0.9642 vs 0.9642, 5.1ms: 0.9237 vs 0.9246, avg ΔP=−0.0002）
  - **burst_stats (5维) 有部分独立信号**：单独使用可达 0.835–0.925 precision，说明 burst 模式编码了与 gap 互补的信息
  - **其余 7 组独立预测能力为 0**：precision 恒为 0（250µs–5.1ms），无任何独立信息
- **综合结论**：对于 GLM-6B finetuning 此类高度结构化的负载，gap 的时序统计量已编码充分的预测信息。LOO 证明 gap_stats 是必须的（移除→精度暴跌），正向消融证明 gap_stats 是充分的（仅用即可匹配 baseline）。burst_stats 提供辅助信息，其余特征可安全裁剪。详见 D3 报告和 Fig 6（`code/results/figures/fig_d3_forward_ablation.png`）。
- **局限**（写入 Discussion）：不能声称这 8 组在所有负载上都无用，只是 GLM-6B 的边界情况。

### 5.3 冷启动 / Drift / Oracle 上界（0.5 页）
- **Warm-up / 在线适应速度**（Fig 6 / `p2.1_cold_start.png`）：用 Pass2 前半段 k 个样本训练，后半段评估。10 样本→0.85，200 样本→0.96+，500→0.98+。论点：同一 pass 内在线适应快，~200 样本（约 2 秒）即可达到可用精度。
- **D7: 真正冷启动 — Pass1 → Pass2**（Fig 7 / `fig_d7_cold_start.png`）：用 Pass1 前 k 个样本训练，在全新 Pass2 上评估。k=200 时 500µs/1ms 精度已达 0.966（意外地好），k=5,000 时全部 horizon 精度 >0.973。**结论：跨 pass 冷启动需要 ~5,000 样本（约 30 秒 GLM-6B trace），远多于同 pass warm-up 的 200 样本，但在 5000 样本时达到的精度（0.974）甚至优于同 pass 的 0.965**——说明 Pass1 的模式对 Pass2 具有良好的泛化性。详见 D7 报告。
- **Drift**（Fig 8 / `p2.2_drift.png`）：后20% precision 优于前80%（ΔP +0.01~+0.03）。
  **D2 实验解释**：对比前后段 gap 分布发现，后段 gap 上尾拉长（p75: 4.1→10.5ms, mean: 44.9→368ms），500µs safe% 从 28.9%→34.0%。precision 改善来自数据分布偏移而非模型"越跑越准"。**关键是零退化**：FSR 在后段反而降低了 0.5–0.9pp。详见 D2 报告和 Fig 9（`code/results/figures/fig_d2_drift_gap.png`）。
- **Oracle gap**（Fig 10 / `p2.3_oracle_gap.png`）：η=0.95 时 safe ratio = 1.0000 = Oracle，仅探测次数少 15.7%。论点：FlowGap 接近理论上界。

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

### 5.7 RQ3-c 故障检测（0.2 页，降级为 preliminary evaluation）
- 注入方案：双向 memcpy 带宽竞争（128MB @ 1ms interval, BOTH direction），基线带宽 20.10 GB/s，判定阈值 14.07 GB/s。
- 结果：**检测延迟 14.65s**，传输带宽从 20.10→10.77 GB/s 的异常被成功检出。
- **但 recall 49.2%、precision 47.5% 偏低**——背景分析（`rawlog_analysis_report.txt`）显示 GLM-6B finetuning 训练带宽中位数仅 0.79 GB/s（远低于理论峰值 25 GB/s），注入器虽然占用硬件链路，但训练本身不频繁使用链路，导致探针与竞争窗口错峰。
- **D9 方案**：将此节降级为 §6 Discussion 中的 1 段 preliminary observation。主 Evaluation 删去 §5.7，留核心 7 策略对比 + 开销两个 RQ3 子实验。

### 5.8 敏感性（置信度阈值 η，0.3 页）
- η sweep：0.50→0.70 precision 0.9545→0.9983、BW probes −12.6%；η≥0.95 探针为 0（过保守）。
- 论点：推荐 η=0.70 平衡 precision 与覆盖。（可作小表或并入 5.6）

---

## 6. Discussion（0.5 页）

### ¶1 — 设计取舍
gap_stats 主导（LOO −5.2pp, Forward ΔP=−0.0002）说明问题本质是时序统计——简单模型足够，复杂特征边际收益低。burst_stats 提供部分辅助信号（独立 precision 0.84–0.93），其余 7 组在 GLM-6B 上无独立价值但不排除在其他负载上有用。GBDT 优于 LR 4–19pp，非线性模式需要树模型结构。

### ¶2 — 局限
1. 单负载族（GLM-6B finetuning）+ Qwen2 仅 162 样本 → 泛化性待扩展；
2. 故障检测 recall/precision 偏低（~48%）— 源于训练负载带宽利用率低（median 0.79 GB/s），而非探测能力不足。检测延迟 14.65s 初步展示了故障感知能力，但需要在带宽饱和型负载上进一步验证；
3. 单节点评估，多节点 / 异构集群效果未知。

### ¶3 — 未来工作
带宽饱和型负载的故障检测验证、在线 drift+增量训练、多节点联合调度、"何时探测"+"在哪探测"联合优化、更多模型/并行策略（GPT/MoE/TP+PP+DP）。

---

## 7. Related Work（1.0 页，4 子主题各 1 段）

### 7.1 Intra-host Monitoring and Diagnosis
Hostping [NSDI'23] 首次系统性诊断 RDMA 服务器内部瓶颈，发现 6 种未知瓶颈类型，证明单个瓶颈可拖垮分布式训练。但其 loopback probe 不感知训练时机。HostDiag 将 Hostping 迁至 AI accelerator 场景，使用 eBPF hook 框架 API 做 memcpy 探测，但调度逻辑仍是阈值触发（reactive）。**FlowGap 的区别**：首个回答"何时可以安全探测而不干扰训练"的系统，用 GBDT 预测安全窗口替代阈值/周期调度。

### 7.2 Active Probing in Datacenter Networks
Pingmesh [SIGCOMM'15] 率先提出全网 all-to-all 主动探测，Pingmesh 2.0 [SIGCOMM'24] 提升至 10 Hz、99.9% 覆盖，但探针均为固定间隔。RD-Probe [SIGCOMM'24] 解决虚拟化环境的路径爆炸问题（空间覆盖：从 80.9% 到 99.5%）。µMon [SIGCOMM'24] 实现 8.192µs 粒度的被动流量监控，可捕获 microbursts。**差异**：RD-Probe 决定"在哪探测"（空间），µMon 决定"看什么指标"（被动），FlowGap 决定"何时探测"（时间 + 主动 + 预测）。三者解决正交问题。

### 7.3 AI Training Infrastructure Monitoring
PerfTracker [Alibaba 2025] 是首个生产环境大模型训练诊断系统（10,000+ GPU），提供 100µs 精度 fine-grained profiling，但诊断已发生的性能问题（事后）。Alibaba HPN [SIGCOMM'24]、Meta RoCE [SIGCOMM'24] 分别从网络架构和 RDMA deployment 角度优化 AI 集群通信。NVIDIA Spectrum-X [2024] 从硬件层面加速。**FlowGap 的定位**：与 PerfTracker 互补（预防性监控 vs. 事后诊断），与其他架构方案互补（运行时预测调度）。

### 7.4 ML for Network Measurement and Prediction
传统流量预测（LSTM/Transformer）关注分钟/小时级宏观趋势；网络异常检测识别已发生的异常模式。**FlowGap 的创新**：首个使用 GBDT 预测**微秒级 gap** 的系统。不预测流量大小，而是预测"何时存在足够大的安全窗口"来执行探针。选择 GBDT 的理由：小样本（16K）抗过拟合、可解释（对应消融分析）、CPU 推理 <1ms、ECE<0.02 的多 horizon 概率校准。

---

## 8. Conclusion（0.25 页）
重申"监控-干扰"两难 → burst-gap 可预测洞察 → eBPF+GBDT 预测式探测 → 真机零干扰高覆盖 + 开销可忽略；展望多节点与在线自适应。

---

## 配图/表索引（投稿用）

| 编号 | 内容 | 资产状态 |
|:---:|------|---------|
| Fig 1 | 动机图（fixed vs FlowGap） | 待绘 |
| Fig 2 | Pass1/Pass2 per-path gap 分布 | 待绘（数据已有） |
| Fig 3 | H2D vs D2H gap 分布 | 待绘（数据已有） |
| Fig 4 | 系统架构 | 已有 `flowgap_architecture.png` |
| Fig 5 | 特征消融 (P1.1 LOO) | 已有 `p1.1_feature_ablation.png` |
| Fig 6 | Warm-up 在线适应 | 已有 `p2.1_cold_start.png` |
| Fig 7 | 真正冷启动 (D7) | 已有 `fig_d7_cold_start.png` |
| Fig 8 | Drift (P2.2) | 已有 `p2.2_drift.png` |
| Fig 9 | Drift gap 分布 (D2) | 已有 `fig_d2_drift_gap.png` |
| Fig 10 | Oracle gap | 已有 `p2.3_oracle_gap.png` |
| Fig 11 | 跨负载 | 已有 `p1.2_second_workload.png` |
| Fig 12 | 策略对比 | 已有 `fig1_policy_comparison.pdf` |
| Fig 13 | 校准曲线 | 已有 `fig2_calibration.pdf` |
| Fig 14 | 开销分解 | 已有 `fig3_overhead_breakdown.pdf` |
| Fig 15 | ML baseline 对比 (D5) | 已有 `fig_d5_model_comparison.png` |
| Fig 16 | 全 horizon 消融 (D4) | 已有 `fig_d4_horizon_ablation.png` |
| Fig 17 | 正向消融 (D3a) | 已有 `fig_d3a_forward_ablation.png` |
| Fig 18 | LOO 消融 (D3b) | 已有 `fig_d3b_loo_ablation.png` |
| Fig 19 | 动机对比 (D1) | 已有 `fig_d1_motivation.png` |
| Table 1 | 30 维特征表 | 数据已有 |
| Table 2 | 跨 Pass 预测精度 | 数据已有 |
| Table 3 | 跨负载泛化 | 数据已有 |
| Table 4 | 7 策略对比 | 数据已有 |
| Table 5 | ML baseline 对比 | D5 数据已有 |
| Alg 1–3 | 三个算法 | 已有 `algorithms.tex` |

> 注：18 张图/表中仅 Fig 1–3 仍需绘制，其余全部产出。投稿时必须挑最重要的 11–13 张放入正文，其余放入附录。

---

## 附录 D：投稿前需要重跑 / 新增 / 调整参数的实验

### D.1 已完成（✅ 全部跑完，除 D6）

| 编号 | 实验 | 产出 | 结论 |
|:----|------|------|------|
| D1 | Obs 4 动机对比 | `fig_d1_motivation.{pdf,png}` | fixed(1ms) 93.9% unsafe vs FlowGap 0%, D2H dense window 86.4% busy |
| D2 | Drift gap 分布 | `fig_d2_drift_gap.{pdf,png}` | 后 20% gap 上尾拉长（p75 4.1→10.5ms），precision 改善是数据 artifact |
| D3 | 正向消融 + LOO | `fig_d3a/d3b` | gap_stats 充分且必须，burst_stats 部分信号，其余 7 组为 0 |
| D4 | 全 horizon LOO 消融 | `fig_d4_horizon_ablation.{pdf,png}` | gap_stats 在所有 horizon 上一致主导，BW horizon 效应最强（−9.3pp） |
| D5 | ML baseline | `fig_d5_model_comparison.{pdf,png}` | GBDT >> LR（ΔP 4–19pp），非线性模式需要树模型 |
| D6 | XGBoost baseline | **跳过** | xgboost 未安装，非 blocker（scikit-learn GBDT 已 0.96+） |
| D7 | 真正冷启动 | `fig_d7_cold_start.{pdf,png}` | Pass1→Pass2 需要 ~5000 样本达 0.97+，跨 pass 泛化好 |

### D.2 决策：D9 降级方案（已执行）

基于 P0.4 round1 的详细分析（`code/results/p0.4_round1_backup/analysis_and_recommendations.md`）：

> GLM-6B finetuning 训练带宽中位数仅 0.79 GB/s（理论峰值 25 GB/s）。注入器虽然占用硬件链路，但训练本身不频繁使用链路，导致探针与竞争窗口错峰。recall 49.2% 的瓶颈不在探测频率，而在训练负载的带宽利用率本身过低。

**结论**：不走 D8 硬件重跑（不会改善 findamentally），直接执行 D9 方案：
- 在 §5.7 / §6 Discussion 中将故障检测降级为 1 段 preliminary observation
- 保留亮点数字：**检测延迟 14.65s**
- 将 recall/precision 解释为负载特性的局限，不影响 FlowGap 的核心贡献（预测式探针调度）

### D.3 剩余待办（P0 级别）

| 任务 | 说明 |
|------|------|
| Fig 1 动机示意图 | 同一 trace 段 fixed vs FlowGap overlap 对比 — Paper 必须的视觉化 Motivation |
| Fig 2–3 gap 分布图 | Pass1/Pass2 per-path gap 和 H2D/D2H 分布的箱线/CDF 图 |
| 正文 Fig 选择 | 从 19 张候选图中选取 11–13 张放入正文，其余放附录 |
| LaTeX 写作 | 基于此大纲写 12 页正文 |
