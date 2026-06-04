# FlowGap 论文主题

论文题目：  
**FlowGap：基于流量模式预测的低干扰主机内探测系统**

面向平台：  
**Ascend 910A/910B 主机内 workload memcpy traffic**

一句话问题：  
**如何从 Ascend 主机内 workload memcpy activity 中学习 burst-gap 模式，预测 probe 的安全发送窗口，并在尽量不干扰 AI workload 的前提下完成主机内路径/链路探测？**

核心动机：  
Ascend 训练/推理过程中，Host DDR 与 NPU memory 之间存在大量主机内 memcpy activity。这些流量并不是持续稳定的，而是表现为阶段相关的 **burst-gap** 模式。传统固定周期探测无法感知 workload phase，可能与正常 memcpy activity 重叠，造成带宽竞争、iteration jitter 或性能下降。因此，探测系统不应盲目周期性发送 probe，而应识别并预测高置信度的空闲窗口。

核心思想：  
**不精确重建完整主机内流量，而是预测“某条 path/link 在未来是否存在足够长、足够可信的 idle window”。**  
如果预测出的空闲窗口下界满足 probe 时间需求，并且置信度足够高，则在该窗口中触发低干扰探测。

系统主线：

```text
eBPF / runtime hooks 采集 memcpy/sync 相关事件
-> 构建 path/link 级 busy-idle 抽象
-> 学习 workload memcpy activity 的 burst-gap 模式
-> 预测未来 path-aware safe window
-> 基于 confidence gate 决定是否触发 probe
-> 在 safe window 中执行低干扰 probe
-> 分析 probe 结果并反馈给预测器
```

系统模块：

1. **Predictor 预测器**  
   从 eBPF/runtime 事件中学习 path/link 级 burst-gap 模式，预测未来安全窗口，并输出窗口下界与置信度。

2. **Prober 探测器**  
   在预测器给出的高置信度 safe window 中执行 probe，选择目标 path、probe size 和发送时机，尽量避免与 workload memcpy activity 重叠。

3. **Analyzer 分析器**  
   分析 probe latency、bandwidth、jitter 等结果，给出 path/link health 或 probe recommendation，并将 prediction error、overlap、probe cost 等反馈给预测器。

关键挑战：

1. **Irregular and phase-dependent memcpy traffic**  
   主机内 memcpy activity 存在 burst-gap 模式，但 gap 的位置和长度并非固定周期，而是随 data loading、forward、backward、sync、checkpoint 等 workload phase 变化。

2. **API events do not reveal exact link occupation**  
   eBPF/runtime hooks 观测到的是软件层 memcpy submit、sync、completion 等事件，不等价于真实 Host-NPU link occupation。异步排队、stream dependency 和 delayed completion 会导致 busy/idle 边界不确定。

3. **Global idle does not mean path-level idle**  
   全局看似空闲的时间段，不一定意味着所有 path/link 都空闲。安全窗口必须绑定到具体 path/link，否则 probe 仍可能与 hidden shared-link traffic 发生冲突。

4. **Confidence must match real idle windows**  
   预测器不仅要输出 gap estimate，还要输出 calibrated confidence。过度自信会导致 false-safe prediction 和 probe overlap；过度保守会错过可用探测机会，降低 observability。

设计原则：

- **Event-driven，而非 heavy monitoring**  
  使用 runtime/eBPF 事件作为粗粒度观测信号，不依赖高开销、精确链路监控。

- **Path-aware，而非 global-idle only**  
  预测窗口必须绑定到具体 path/link，避免把全局空闲误认为所有路径均安全。

- **Lower-bound prediction，而非平均窗口预测**  
  预测 safe window 的保守下界，使用 safety margin 降低误判安全风险。

- **Confidence-gated probing，而非 fixed-period probing**  
  只有当窗口足够长且置信度足够高时才触发 probe，否则 delay/skip。

- **Online calibration，而非离线固定模型**  
  根据 probe outcome、prediction error 和 overlap 情况在线调整 confidence 与 safety margin。

预测器方案：

预测器可以采用轻量在线模型，而不是复杂深度学习模型。初始方案可设计为：

```text
Path-aware state abstraction
+ online gap-duration lower-bound estimation
+ confidence calibration
```

其中：

- 使用最近的 memcpy event 序列维护 path/link 级状态；
- 从 timestamp、size、direction、stream、device/path、inter-arrival time、recent gap length、recent activity density 等特征中学习 burst-gap 模式；
- 使用在线分位数估计或轻量时序模型预测 gap lower bound；
- 使用历史 prediction hit/miss、probe overlap 和 workload phase pattern 对 confidence 进行校准；
- 输出：
  - target path/link；
  - predicted safe window start time；
  - duration lower bound；
  - confidence；
  - trigger / delay / skip 决策。

触发条件：

```text
Trigger probe only if:

G_lower(p) > T_probe + M
and
Confidence > η
```

其中：

- `G_lower(p)`：path/link `p` 上预测空闲窗口的保守下界；
- `T_probe`：一次 probe 所需时间；
- `M`：安全裕量；
- `η`：置信度阈值。

非目标：

- 不做完整 root cause diagnosis；
- 不精确重建所有物理链路流量；
- 不保证预测每一次 memcpy 的精确开始与结束时间；
- 不将深度学习模型本身作为主要贡献；
- 不追求跨所有硬件平台的通用系统设计；
- 不依赖对训练框架源码的侵入式修改。

预期贡献：

1. 提出一种面向 Ascend 主机内 memcpy activity 的低干扰主动探测问题定义；
2. 识别 workload memcpy traffic 的 burst-gap 结构，并将探测时机建模为 safe-window prediction 问题；
3. 设计 path-aware、confidence-gated 的探测触发机制；
4. 构建 Predictor-Prober-Analyzer 三模块原型系统；
5. 证明相比 fixed-period probing，该方法有潜力降低 probe 对 AI workload 的干扰，同时保留足够的 path/link observability。

论文定位：  
本文不是一个完整的网络故障诊断系统，而是一个面向 Ascend 910A/910B 平台的 **adaptive host-side probing mechanism**。其核心贡献在于：通过学习主机内 workload memcpy activity 的 burst-gap 模式，将探测从固定周期行为转化为基于路径空闲窗口和置信度门控的机会型决策。
