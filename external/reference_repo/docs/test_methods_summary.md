# 主机内测试方法梳理：监控与探测

本文档梳理了当前环境下的主机内测试方法，主要包括基于 eBPF 的监控模块 (`trace_memcpy_numa.py`) 和基于 Ascend C 的探测模块 (`memcpy_benchmark.cpp`)，以及上层的数据分析与诊断模块。

## 1. 监控模块 (trace_memcpy_numa.py)

该模块使用 Python 编写，基于 eBPF (Extended Berkeley Packet Filter) 技术，用于实时监控应用程序调用的 Ascend CL 内存拷贝接口。

### 1.1 代码运行方式

*   **运行命令**:
    ```bash
    # 前台运行
    /usr/bin/python3 trace_memcpy_numa.py --min-size 1024 --output aclrtMemcpy_numa_trace.log

    # 后台运行 (配合 nohup)
    nohup /usr/bin/python3 trace_memcpy_numa.py --min-size 1024 > trace.log 2>&1 &
    ```
*   **参数说明**:
    *   `--min-size`: 设置监控的最小内存拷贝大小 (单位: Byte)，默认为 1MB (1048576)。用于过滤小包，聚焦大块内存传输。
    *   `--output`: 指定 CSV 格式的日志输出路径。

### 1.2 必备软件环境

*   **Python**: Python 3.x (脚本指定解释器为 `/usr/bin/python3`)。
*   **BCC (BPF Compiler Collection)**:
    *   需要安装 `python3-bpfcc` 或 `bcc` 相关包。
    *   脚本依赖 `from bpfcc import BPF`。
*   **Linux Kernel Headers**: 需要安装与当前内核版本匹配的 kernel-devel/kernel-headers，用于 BPF 程序即时编译。
*   **Ascend CANN 软件栈**: 必须安装 Ascend 驱动和固件，脚本会自动查找 `libascendcl.so` 库文件路径。

### 1.3 监控/调用接口

该脚本通过 **uprobe** (User-space Probe) 机制，在用户态 hook 了以下 `libascendcl.so` 中的符号：

1.  **`aclrtSetDevice(int32_t deviceId)`**:
    *   **目的**: 捕获当前线程设置的 Device ID。
    *   **原理**: 维护一个 BPF Hash Map (`thread_device`)，记录 `Thread ID -> Device ID` 的映射关系。
2.  **`aclrtMemcpy`**:
    *   **Hook 点**:
        *   `probe_entry`: 函数入口，记录开始时间戳、源地址、目的地址、拷贝大小、拷贝类型 (H2D/D2H/D2D/H2H)。
        *   `probe_return`: 函数返回，计算耗时 (`delta`)，并结合 `thread_device` 映射表补充 Device ID 信息。
    *   **目的**: 计算内存拷贝的延迟 (Latency) 和带宽 (Bandwidth)，并推断数据流向 (如 Host -> NPU 0)。

### 1.4 输出信息

*   **控制台输出**: 实时打印每条传输记录，包含源/目的、大小、耗时、带宽。
*   **CSV 文件**: 记录详细数据 (PID, TID, Source, Destination, Size_MB, Latency_us, Bandwidth_GBps)，方便后续分析绘图。

---

## 2. 探测模块 (memcpy_benchmark.cpp)

该模块使用 C++ 编写，基于 Ascend C (ACL) 接口，是一个主动式的基准测试工具，用于探测 Host 与 NPU 之间以及不同 NUMA 节点之间的内存拷贝性能。

### 2.1 代码运行方式

*   **编译**:
    需要使用支持 Ascend ACL 的编译器 (如 `g++`) 进行编译，并链接 `libascendcl`、`libnuma` 等库。
    ```bash
    # 示例编译命令 (需根据实际 Makefile 调整)
    g++ -o memcpy_benchmark memcpy_benchmark.cpp -I/usr/local/Ascend/... -L... -lascendcl -lnuma -lpthread
    ```
*   **运行命令**:
    ```bash
    ./memcpy_benchmark
    ```
    (注：代码中未展示具体的命令行参数解析，通常直接运行即可，或根据内部逻辑循环测试)

### 2.2 必备软件环境

*   **C++ 编译器**: 支持 C++11 或更高版本。
*   **Ascend CANN SDK**: 提供 `acl/acl.h` 和 `acl/acl_rt.h` 头文件及动态库。
*   **libnuma**: 用于 NUMA 亲和性设置 (`numa.h`, `numaif.h`)，需要安装 `numactl-devel`。
*   **NPU 驱动/固件**: 必须正常加载，且可以通过 `npu-smi` 查看状态。

### 2.3 监控/调用接口

该程序主动调用了以下关键接口：

1.  **ACL 初始化与管理**:
    *   `aclrtGetSocName`: 获取 SoC 名称 (如 Ascend910B1)，用于判断拓扑结构。
    *   `aclInit`, `aclrtSetDevice`, `aclrtCreateContext`, `aclrtResetDevice`, `aclFinalize`: 标准的 ACL 生命周期管理。
2.  **内存管理**:
    *   `aclrtMalloc`: 分配 Device 侧内存。
    *   `aclrtMallocHost`: 分配 Host 侧内存 (通常是 pinned memory)。
    *   `aclrtFree`, `aclrtFreeHost`: 释放内存。
3.  **数据传输**:
    *   `aclrtMemcpy`: 核心测试接口，用于执行 H2D, D2H, D2D 等拷贝操作。
4.  **NUMA 绑定**:
    *   `numa_allocate_cpumask`, `numa_sched_setaffinity`: 将线程绑定到特定的 CPU 核心。
    *   `numa_allocate_nodemask`, `set_mempolicy`: 设置内存分配策略，确保 Host 内存分配在指定的 NUMA 节点上。
5.  **辅助工具**:
    *   `popen("npu-smi info -t topo", "r")`: 调用系统命令查询 NPU 拓扑信息 (HCCS 链路数量)，用于验证硬件连接状态。

### 2.4 功能逻辑

*   **拓扑感知**: 自动识别 SoC 型号 (910A vs 910B)，并加载对应的 CPU-NPU 亲和性映射表。
*   **性能探测**:
    *   通过循环进行内存拷贝，计算时延 (Latency) 和带宽 (Bandwidth)。
    *   **时延阈值**: 默认硬阈值 35us，超过标记为异常。
    *   **带宽基准**: 设定了同 NUMA (26.5 GB/s) 和跨 NUMA (21.9 GB/s) 的基准值，低于一定比例 (0.8) 视为异常。
*   **故障定位**: 结合 NPU 维度、内存通道维度和 CPU Full-Mesh 链路维度进行故障诊断。

---

## 3. 分析诊断模块 (HostDiag Analyzer)

Analyzer 负责摄取并分析监控模块和探测模块生成的数据，以评估主机内瓶颈的影响并定位故障。

### 3.1 瓶颈定位 (Bottleneck Localization)

*   **数据摄取**:
    *   **流量路径文件 (Flow-path files)**: 由监控模块 (Section 1) 生成。
    *   **资源使用时间序列文件 (Resource usage time-series files)**: 由监控模块生成。
    *   **探测路径文件 (Probe-path files)**: 由探测模块 (Section 2) 生成。
*   **分析方法**:
    *   基于这些序列文件，分析器可以重新计算任何时刻任何主机内路径的带宽。
    *   检索小包探测获得的时延数据。
    *   利用不同路径之间的相关性并控制变量，准确定位主机内瓶颈链路的具体位置。
*   **瓶颈特征**:
    *   带宽低于预设阈值 $bw_{th}$。
    *   或者，时延超过预设阈值 $lat_{th}$。

### 3.2 严重性评估 (Severity Assessment)

在定位瓶颈后，分析器使用以下指标评估主机内链路异常的严重程度：

*   **(a)** 带宽低于阈值 $bw_{th}$。
*   **(b)** 时延高于阈值 $lat_{th}$。
*   **(c)** 异常持续时间超过阈值 $time_{d}$。
*   **(d)** 异常时间占比超过阈值 $time_{r}$。
*   **(e)** 异常链路比例超过阈值 $link_{r}$。
*   **(f)** DML (Data Manipulation Language) 任务吞吐量异常下降。

### 3.3 故障分级 (Fault Classification)

基于上述指标，分析器执行分级评估流程：

1.  **P0 级故障 (严重故障)**:
    *   条件：满足 (a) 或 (b) 中的至少一项 **且** 满足 (c)-(e) 中的至少一项。
    *   含义：确认为导致严重故障的关键主机内瓶颈链路。
    *   处理：数据转发至 DCN 管理系统进行统一处理。

2.  **P1 级故障 (重要故障)**:
    *   条件：满足 (a) 或 (b) 中的至少一项 **但** 不满足 (c)-(e) 中的任何一项。
    *   含义：被归类为重要的主机内瓶颈链路。
    *   处理：数据转发至 DCN 管理系统进行统一处理。

3.  **P2 级告警 (警告)**:
    *   条件：不满足 (a)-(e) 中的任何一项，但触发了指标 (f)。
    *   含义：性能下降可能由 DML 任务配置或调度机制引起。
    *   处理：向应用侧报告记录的数据，以协助排查任务级性能问题。

### 3.4 统一 Schema 故障遥测聚合 (Aggregate Fault Telemetry Through Unified Schema)

在完成原始数据处理后，Analyzer 使用 UFTS (Unified Fault Telemetry Schema) 表示结果，并将其报告给 DCN 管理系统，以支持跨层故障关联和根因分析。数据报告分为两层：**故障事件数据** (Fault Event Data) 和 **故障指标数据** (Fault Metric Data)。

#### 3.4.1 故障事件数据 (Fault Event Data)

故障事件数据通过 UFTS 的编码字段描述分析后的故障信息。结构如下：

*   **Basic Fault Description Group**: 每个 `fault_device_id` 字段及其后续的一组 `fault_metric` 值共同描述单个故障设备的多个指标。
*   **Metric Flag**: 在每个 `fault_device_id` 之前有一个 `metric_flag` 字段，用于指示后续包含了哪些类型的指标值（每一位代表一种指标类型，置 1 表示包含）。
*   **Device Count**: 定义了每个故障事件数据包中包含的 Basic Fault Description Group 的数量。

例如：如果 `metric_flag` 的第 0、2、5 位为 1，则表示 `fault_device_id` 后面跟随了三组对应的 `fault_metric` 值。

#### 3.4.2 故障指标数据 (Fault Metric Data)

如果 DCN 管理系统收到故障事件数据后需要进一步的交叉对比分析，它可以请求 Analyzer 提供更详细的故障指标数据。该数据包含 Monitor 和 Prober 捕获的原始数据。

系统根据管理平台的请求，检索相应时间段内的流量路径文件、探测路径文件和资源使用时间序列文件，构建如下格式的数据：

*   **`fault_id` (32-bit)**: 唯一标识符，与故障事件数据对应。
*   **`reserved` (64-bit)**: 全零数据，用于区分故障指标数据和故障事件数据。
*   **`data_type` (32-bit)**: 指示传输的数据文件类型。
*   **`raw_data`**: 故障数据的原始记录。

#### 3.4.3 传输优化

*   **二进制编码**: 故障事件数据和故障指标数据均采用二进制编码进行传输，以减少开销并提高系统响应速度。
*   **数据区分**: 利用时间戳的 64 位秒级部分来区分故障事件数据和故障指标数据的传输，防止数据混淆。

---

## 4. 总结对比

| 特性 | 监控模块 (trace_memcpy_numa.py) | 探测模块 (memcpy_benchmark.cpp) | 分析诊断模块 (HostDiag Analyzer) |
| :--- | :--- | :--- | :--- |
| **类型** | **被动监控** (Passive Monitoring) | **主动探测** (Active Probing) | **数据分析与诊断** (Data Analysis) |
| **语言** | Python + eBPF (C) | C++ | (逻辑层，通常集成在管理平台) |
| **核心机制** | **uprobe** (Hook `aclrtMemcpy`) | **Direct Call** (调用 `aclrtMemcpy`) | **多源数据关联分析** & **UFTS 统一上报** |
| **用途** | 观察**现有应用** (如训练任务) 的真实行为、流量特征和性能瓶颈。 | 压测硬件极限性能，**诊断**硬件故障、拓扑连接问题或驱动问题。 | 定位瓶颈链路，评估严重性，输出分级告警 (P0/P1/P2) 及原始数据。 |
| **对业务影响** | 极低 (旁路监控) | 高 (占用计算/内存资源，通常单独运行) | 无 (离线或旁路分析) |
| **NUMA 关注点** | 记录发起调用的 CPU 所在 NUMA，分析应用亲和性。 | 主动绑定 CPU/内存到指定 NUMA，测试跨 NUMA 性能损耗。 | 综合分析跨 NUMA 流量与性能下降的相关性。 |
