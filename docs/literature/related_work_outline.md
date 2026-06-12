# FlowGap Related Work - Literature Review

**Updated**: 2026-06-10  
**Status**: Initial draft based on web search results

---

## 搜索策略记录

### 已完成的搜索
1. **AI加速器网络监控** (2024-06-10)
   - Query: "AI accelerator network monitoring GPU TPU Ascend collective communication performance 2023 2024"
   - Results: 5 papers/articles (Google Cloud AI Hypercomputer, NVIDIA Spectrum-X, GPU-to-GPU communication benchmark, Meta RoCE, NVIDIA SuperNICs)

2. **训练性能诊断** (2024-06-10)
   - Query: "training performance diagnosis AI workload bottleneck detection machine learning systems"
   - Results: 5 papers/articles (GPU bottleneck diagnosis, PerfTracker, PEFT profiling, AI workload optimization)

3. **主动探针和数据中心监控** (2024-06-10)
   - Query: "active probing non-intrusive measurement datacenter network low overhead 2022 2023 2024"
   - Results: 4 papers (RD-Probe SIGCOMM'24, network-stack latency profiling, µMon SIGCOMM'24)

---

## 相关工作分类体系

基于 FlowGap 的定位（AI基础设施监控 + 主动探针 + 低干扰），相关工作分为以下主题：

### 1. AI 加速器网络性能监控
**核心问题**: 如何监控 GPU/TPU 集群的网络性能（带宽、延迟、拥塞）

#### 1.1 GPU 集群互连性能测量
- **[arXiv'24] Exploring GPU-to-GPU Communication** (De Sensi et al.)
  - 3个超算系统 (Alps, Leonardo, LUMI) 的 4096 GPU 网络性能评测
  - 关注 intra-node (NVLink) 和 inter-node (InfiniBand/Slingshot) 性能
  - **关键发现**: 仍有未利用的带宽，存在优化空间
  - **与 FlowGap 关系**: 类似的 GPU 集群场景，但他们是 benchmark 测试，FlowGap 是生产环境在线监控

#### 1.2 商业 AI 网络解决方案
- **[NVIDIA'24] Spectrum-X Ethernet Platform**
  - RoCE adaptive routing + BlueField-3 SuperNIC
  - 800 Gb/s 数据吞吐，4x 传统以太网带宽
  - 专注于硬件优化，缺少预测式探针调度
  
- **[Meta SIGCOMM'24] RDMA over Ethernet for AI Training**
  - 数万 GPU 的 RoCE 网络设计
  - 两层网络分离：Frontend (数据加载) + Backend (训练通信)
  - **与 FlowGap 区别**: Meta 关注网络架构设计，FlowGap 关注运行时监控和低干扰探测

#### 1.3 加速器性能瓶颈诊断
- **[Google/Microsoft Research]** 70% 训练时间被 I/O 操作消耗
- **[Hyperbolic'25] GPU Bottleneck Diagnosis**
  - 识别数据加载、CPU 预处理、网络通信瓶颈
  - 使用 nvidia-smi, TensorFlow Profiler, PyTorch Profiler
  - **局限**: 被动监控，无法主动探测链路健康

---

### 2. 训练性能分析与诊断
**核心问题**: 如何在生产环境中诊断大模型训练的性能问题

#### 2.1 在线性能分析工具
- **[Alibaba arXiv'25, Product] PerfTracker**
  - **关键贡献**: 首个生产环境的大模型训练在线诊断系统
  - **方法**: Fine-grained profiling (CUDA kernel + Python function + 硬件监控)
  - **规模**: 10,000+ GPU 集群
  - **诊断能力**: 慢节点定位、函数级瓶颈、Hang 问题
  - **开销**: 基于 Torch profiler + nsys，100µs 精度
  - **与 FlowGap 关系**: 
    - 相似点: 都是生产环境在线系统，都关注低开销
    - 区别: PerfTracker 诊断已发生的性能问题，FlowGap **预测并避免**探针干扰

#### 2.2 框架内置 Profiler
- TensorFlow Profiler, PyTorch Profiler
- **局限**: 高开销（5-20%），不适合持续监控
- FlowGap 定位: 补充工具，在不影响训练的前提下持续探测网络健康

---

### 3. 数据中心网络主动探针
**核心问题**: 如何在复杂网络中高效探测，同时保证覆盖率和可扩展性

#### 3.1 覆盖率保证的主动探针
- **[Huawei & Peking SIGCOMM'24] RD-Probe**
  - **问题**: 生产环境覆盖率不足 (80.9%) 导致故障漏检
  - **方法**: Randomized + Deterministic 混合方法
  - **成果**: 1个月内覆盖率提升至 99.5%
  - **挑战**: 虚拟化、随机化路由、路径爆炸 (O(10^87) 链路组合)
  - **与 FlowGap 关系**:
    - RD-Probe 关注 Layer-2 物理链路覆盖，FlowGap 关注 **时间窗口选择**
    - RD-Probe 是"在哪探测"，FlowGap 是"何时探测"
    - 互补关系: RD-Probe 确定探测路径，FlowGap 预测安全时机

#### 3.2 微秒级网络监控
- **[Nanjing Univ. SIGCOMM'24] µMon**
  - **粒度**: 8.192 µs 微秒级监控
  - **方法**: WaveSketch (基于小波变换的流量率压缩)
  - **开销**: 5 Mbps/host (流量率)，31-82 Mbps/switch (拥塞事件)
  - **能力**: 捕获 microbursts，replay 拥塞事件
  - **与 FlowGap 区别**: µMon 被动监控，FlowGap 主动探针 + 预测式调度

#### 3.3 Host 内网络诊断
- **[ByteDance NSDI'23] Hostping** (待搜索详细信息)
  - Host 内延迟监控和故障诊断
  - **与 FlowGap 关系**: Hostping 是 Host 内，FlowGap 是 intra-host (Ascend HCCS)
  - 需要对比 Hostping 的探针调度策略

---

### 4. 预测式网络管理
**核心问题**: 使用 ML 预测网络行为，优化资源分配或故障预防

#### 4.1 网络流量预测
- (待补充文献: 基于 LSTM/Transformer 的流量预测)
- **与 FlowGap 区别**: 传统流量预测关注宏观趋势，FlowGap 预测微秒级 gap

#### 4.2 ML-based 网络异常检测
- (待补充文献: 异常检测相关工作)
- **与 FlowGap 区别**: 检测已发生的异常 vs 预测安全探针窗口

---

### 5. eBPF 网络监控
**核心问题**: 内核级监控的开销和性能权衡

#### 5.1 eBPF Tracing 开销研究
- (待补充文献: eBPF 性能开销测量)
- FlowGap 使用 eBPF uprobe 监控 AscendCL API
- **需要对比**: eBPF 本身的开销 vs FlowGap 探针开销

---

## FlowGap 的独特贡献与定位

### 与现有工作的核心区别

| 维度 | 现有工作 | FlowGap |
|------|---------|---------|
| **监控时机** | 被动监控 (µMon, 传统 Profiler) | 预测式主动探针 |
| **探针调度** | 固定间隔/随机 (RD-Probe) | GBDT 预测安全窗口 |
| **关注对象** | 已发生的性能问题 (PerfTracker) | 预防探针干扰训练 |
| **目标网络** | 通用数据中心网络 | AI 加速器 intra-host 网络 |
| **覆盖维度** | 空间覆盖 (哪些链路) | 时间覆盖 (何时探测) |
| **安全保证** | 尽力而为 | 100% 安全率 (0% unsafe probe) |

### FlowGap 的关键创新点
1. **首个 burst-gap 感知的探针系统** - 利用 AI 训练的通信模式
2. **预测式低干扰探针** - GBDT 模型预测安全时机
3. **多 horizon 置信度校准** - 适配不同探针类型 (TINY 50µs, BW 5ms)
4. **极低开销** - 0.0643% (488 探针 / 1200s 训练)
5. **生产验证** - Ascend 910B 集群实际训练任务

---

## §3 - Hostping 详细信息（已找到）

**Hostping: Diagnosing Intra-host Network Bottlenecks in RDMA Servers**
- **发表**: NSDI 2023, pp.15–29
- **作者**: Kefei Liu, Zhuo Jiang (ByteDance), Jiao Zhang (BUPT/PML), et al.
- **BibTeX key**: `liu2023hostping`
- **核心贡献**:
  - 首个专注于 intra-host 网络瓶颈诊断的系统
  - 方法: loopback tests（RNICs ↔ host endpoints）测量延迟和带宽
  - 发现 6 个此前未知的 intra-host 瓶颈类型
  - 场景: RDMA 服务器，分布式机器学习训练中单个 intra-host 瓶颈能拖垮整个系统

- **与 FlowGap 的关键区别**:
  - Hostping: RDMA (PCIe/QPI/UPI) 层面，诊断**已发生**的瓶颈，不感知训练负载时机
  - FlowGap: Ascend HCCS 层面，**预测**安全探测窗口，训练感知调度
  - Hostping 的 loopback probe 是否干扰训练？论文未讨论
  - **FlowGap 的核心价值**: 解决 Hostping 未解决的问题 — "何时可以安全探测"

---

## §4 - Microburst 相关工作（已找到）

**Uncovering Secrets of Microbursts in Datacenter Network Traffic**
- **发表**: CNSM 2024, DOI: 10.23919/CNSM62983.2024.10814641
- **作者**: Mohammad Hosseini, Sina Darabi, Patrick Eugster (USI)
- **核心贡献**: BurstVision 工具，从流量 trace 中提取 microburst 特征
- **发现**: 不同应用的 microburst 特征差异显著，90% of bursts < 200µs
- **与 FlowGap 关系**:
  - FlowGap 观察到的 burst/gap 模式与 datacenter microburst 研究相关
  - FlowGap **利用** burst 规律性预测 gap；而 BurstVision 关注 **减轻** burst 影响

**Alibaba HPN: A Data Center Network for Large Language Model Training**
- **发表**: SIGCOMM 2024（最具影响力论文 #1）
- **作者**: Kun Qian et al. (Alibaba Cloud)
- **核心贡献**: 专为 LLM 训练设计的数据中心网络 HPN
- **与 FlowGap 关系**: 相同的 AI 训练网络场景，但 HPN 关注网络架构，FlowGap 关注运行时监控

---

## Related Work 论文大纲（SoCC 2026 版）

### 章节结构建议（~1.5 页）

```
§ Related Work

§X.1 Intra-host Network Monitoring and Diagnosis
  - Hostping [NSDI'23]: loopback-based RDMA intra-host diagnosis
    → FlowGap 区别: training-aware, predictive scheduling, Ascend HCCS
  - HostDiag (TODO: 搜索是否有后续论文)

§X.2 Active Probing and Coverage in Datacenter Networks
  - RD-Probe [SIGCOMM'24]: scalable coverage in complex paths
    → FlowGap 区别: space coverage vs. time-window selection
  - µMon [SIGCOMM'24]: microsecond-level passive monitoring
    → FlowGap 区别: active vs. passive; scheduled probing vs. always-on

§X.3 AI Training Infrastructure Monitoring
  - PerfTracker [Alibaba arXiv'25]: online diagnosis for LLM training (10K+ GPU)
    → FlowGap 区别: FlowGap focuses on probe interference prevention
  - Alibaba HPN [SIGCOMM'24]: network design for LLM training
    → FlowGap 区别: infrastructure design vs. runtime monitoring
  - Meta RoCE [SIGCOMM'24]: RDMA over Ethernet at scale
    → FlowGap 区别: network architecture vs. workload-aware probing

§X.4 ML-based Network Measurement
  - ML for network anomaly detection (survey-level reference)
  - GBDT / tree-based models for network classification
    (FlowGap 使用 GBDT 的理由: 小数据集、可解释性)
```

---

## BibTeX 条目（已验证）

```bibtex
@inproceedings{liu2023hostping,
  author    = {Kefei Liu and Zhuo Jiang and Jiao Zhang and Haoran Wei and
               Xiaolong Zhong and Lizhuang Tan and Tian Pan and Tao Huang},
  title     = {Hostping: Diagnosing Intra-host Network Bottlenecks in {RDMA} Servers},
  booktitle = {20th USENIX Symposium on Networked Systems Design and Implementation
               ({NSDI} 23)},
  year      = {2023},
  pages     = {15--29},
  publisher = {USENIX Association},
  address   = {Boston, MA},
  url       = {https://www.usenix.org/conference/nsdi23/presentation/liu-kefei}
}

@inproceedings{qian2024hpn,
  title     = {Alibaba {HPN}: A Data Center Network for Large Language Model Training},
  author    = {Kun Qian and others},
  booktitle = {Proceedings of the {ACM} {SIGCOMM} 2024 Conference},
  year      = {2024},
  publisher = {ACM},
  doi       = {10.1145/3651890.3672265}
}

@inproceedings{meta2024rdmaai,
  title     = {{RDMA} Over Ethernet for Distributed Training at Meta Scale},
  booktitle = {Proceedings of the {ACM} {SIGCOMM} 2024 Conference},
  year      = {2024},
  publisher = {ACM},
  doi       = {10.1145/3651890.3672233}
}

@inproceedings{hosseini2024microbursts,
  author    = {Mohammad Hosseini and Sina Darabi and Mohammad Nakhjiri and Patrick Eugster},
  title     = {Uncovering Secrets of Microbursts in Datacenter Network Traffic},
  booktitle = {20th International Conference on Network and Service Management ({CNSM})},
  year      = {2024},
  doi       = {10.23919/CNSM62983.2024.10814641}
}

% RD-Probe and µMon — need DOI from SIGCOMM'24 proceedings (NEED_MANUAL_CHECK)
@inproceedings{rdprobe2024,
  title     = {{RD-Probe}: Scalable Monitoring With Sufficient Coverage in Complex
               Datacenter Networks},
  booktitle = {Proceedings of the {ACM} {SIGCOMM} 2024 Conference},
  year      = {2024},
  note      = {NEED\_MANUAL\_CHECK: verify author names and DOI}
}

@inproceedings{umon2024,
  title     = {$\mu${Mon}: Empowering Microsecond-level Network Monitoring with Wavelets},
  booktitle = {Proceedings of the {ACM} {SIGCOMM} 2024 Conference},
  year      = {2024},
  note      = {NEED\_MANUAL\_CHECK: verify author names and DOI}
}
```

---

## 待人工确认的事项（NEED_MANUAL_CHECK）

1. **RD-Probe 作者** - 搜索结果显示 Huawei + 北京大学，需确认作者列表
2. **µMon 作者** - 搜索结果显示南京大学，需确认完整信息
3. **PerfTracker DOI** - arXiv 版本 2506.08528，需确认是否已正式发表
4. **HostDiag** - 是否有后续发表的工作（区别于 Hostping）

---

## Sources

### Hostping
- [Hostping: NSDI'23 官方页面](https://www.usenix.org/conference/nsdi23/presentation/liu-kefei)
- [Hostping PDF](https://jiao-bupt.github.io/papers/Hostping_NSDI.pdf)

### AI 训练网络
- [Alibaba HPN SIGCOMM'24](https://doi.org/10.1145/3651890.3672265)
- [Meta RoCE SIGCOMM'24](https://doi.org/10.1145/3651890.3672233)
- [PerfTracker arXiv'25](https://arxiv.org/html/2506.08528v3/)
- [GPU-to-GPU Supercomputer benchmarks arXiv'24](https://arxiv.org/html/2408.14090v2/)

### Microburst
- [BurstVision CNSM'24](https://doi.org/10.23919/CNSM62983.2024.10814641)
- [Most Influential SIGCOMM Papers 2024](https://resources.paperdigest.org/2025/09/most-influential-sigcomm-papers-2025-09-version/)

### 主动探针
- [RD-Probe SIGCOMM'24](https://cs.stanford.edu/~keithw/sigcomm2024/sigcomm24-final696-acmpaginated.pdf)
- [µMon SIGCOMM'24](https://cs.stanford.edu/~keithw/sigcomm2024/sigcomm24-final305-acmpaginated.pdf)
