# 监控器-探测器联动与排障手册（yhj/n）

## 1. 目标与适用范围
- 目标：把训练/微调过程中的 `aclrtMemcpy` 流量变化，转化为“何时触发深度探测”的自动决策链路。
- 场景：Ascend 环境下，背景流（如 MindFormers 训练）持续运行，监控链路自动感知链路拥塞并触发探测。
- 本手册覆盖：
  - 联动架构与文件映射
  - 当前运行逻辑（监控、聚合、触发、探测）
  - 常见失败模式与排障步骤
  - `yhj/n` 工作区文件清单（未知用途留占位）

---

## 2. 联动架构（从背景流到探测结果）

### 2.1 数据流主链路
- 背景流进程调用 AscendCL `aclrtMemcpy`
- eBPF 脚本 hook `aclrtMemcpy` 入口/返回，采集单次 memcpy 数据
- 脚本输出两类日志：
  - 原始日志：逐调用记录（raw）
  - 聚合日志：按时间窗、按 `src->dst` 聚合（monitor input）
- Adaptive Daemon 读取聚合日志，按阈值判断是否异常
- 异常时向 probe 进程发 `SIGUSR1`
- Probe 收到信号后执行一轮矩阵探测并输出结论

### 2.2 关键进程
- eBPF 监控进程：`trace_memcpy_numa.py`
- 自适应守护进程：`npu_adaptive_daemon`
- 探测进程：`memcpy_benchmark`

---

## 3. 文件与角色映射（必须知道）

- 监控器脚本  
  [trace_memcpy_numa.py](file:///root/hostdiagv2/trace_memcpy_numa.py)
  - 参数：`--min-size`、`--window-ms`、`--agg-output`
  - 功能：hook memcpy、写 raw、做 `src->dst` 窗口聚合

- 守护进程源码  
  [npu_adaptive_daemon.cpp](file:///root/hostdiagv2/npu_adaptive_daemon.cpp)
  - 功能：读取聚合文件、按阈值判断、发送 `SIGUSR1`

- 守护进程二进制  
  [npu_adaptive_daemon](file:///root/hostdiagv2/npu_adaptive_daemon)

- 一键启动  
  [start_monitor_stack.sh](file:///root/hostdiagv2/start_monitor_stack.sh)
  - 功能：启动 probe/eBPF/daemon，准备日志与 pid

- 一键停止  
  [stop_monitor_stack.sh](file:///root/hostdiagv2/stop_monitor_stack.sh)
  - 功能：按 pid + 兜底 pkill 停止三进程

- 运行日志目录  
  [logs](file:///root/hostdiagv2/logs)
  - `aclrtMemcpy_numa_raw.log`：原始逐调用日志
  - `daemon.log`：守护进程日志
  - `ebpf.log`：监控器终端输出重定向
  - `probe.log`：探测器输出
  - `*.pid`：三进程 pid 文件

---

## 4. 当前监控逻辑（详细）

### 4.1 eBPF 原始采集逻辑
- 在 `aclrtMemcpy` 入口记录：
  - `count`（字节）
  - `ts`（start ns）
  - 地址参数与 kind
- 在返回点记录：
  - `delta`（持续时间 ns）
  - `end_ns = start_ns + delta`
- 输出 raw 行：包含 `Size_MB / Latency_us / Bandwidth_GBps / Start_ns / End_ns`

### 4.2 第三层聚合（src->dst）
- 目标：以 `src->dst` 链路维度反映拥塞，而不是单次 memcpy 瞬时值
- 聚合维度：
  - 时间窗：`window-ms`
  - key：`(Source, Destination)`
- 聚合方法：
  - 对每条 memcpy 区间 `[start_ns, end_ns)` 与窗口做重叠
  - 按重叠比例分摊 bytes 到对应窗口
  - 输出每个窗口中每条 `src->dst` 的 `Bytes_MB`、`Bandwidth_GBps`
- 聚合输出文件（monitor input）默认：
  - `/root/hostdiagv2/aclrtMemcpy_numa_trace.log`

### 4.3 Daemon 触发逻辑
- 输入：聚合日志（CSV）或原始日志（兼容）
- 判定字段：
  - 聚合模式读取 `Bandwidth_GBps`（第6列）并换算 `MB/s`
- 触发条件：
  - `low < rate_mbps < high`
  - 且满足 cooldown 时间间隔
- 动作：
  - 从 `probe.pid` 取 pid，发送 `SIGUSR1`
  - 失败时打印 `errno`

### 4.4 Probe 执行逻辑
- 收到 `SIGUSR1` 后，执行一轮：
  - Latency 扫描
  - Bandwidth 扫描
- 注意：若分类后“无异常”，可能仅看到 `Triggered` + `Finished`，没有详细异常块输出（属设计行为）

---

## 5. 运行建议（推荐参数）

### 5.1 一键启动
```bash
/root/hostdiagv2/start_monitor_stack.sh
```

### 5.2 常用参数覆盖
```bash
MIN_SIZE=1048576 \
WINDOW_MS=100 \
LOW_MBPS=800 \
HIGH_MBPS=26000 \
COOLDOWN_SEC=3 \
/root/hostdiagv2/start_monitor_stack.sh
```

### 5.3 一键停止
```bash
/root/hostdiagv2/stop_monitor_stack.sh
```

---

## 6. 踩坑与排障（重点）

### 6.1 表面现象：背景流在跑，但 eBPF 看起来无输出
- 原因：
  - 训练阶段存在正常 memcpy 空窗
  - `MIN_SIZE` 过大导致被过滤
  - 当前业务更多走 async 路径（仅 hook memcpy 时会漏）
- 排查：
  - 看 `logs/ebpf.log` 是否有新行
  - 看 `logs/aclrtMemcpy_numa_raw.log` 行数是否增长

### 6.2 表面现象：daemon 不触发
- 常见原因：
  - 守护进程读的是聚合日志，但聚合文件无新增
  - 阈值单位混淆（daemon 用 MB/s，聚合输出是 GB/s）
  - 刚启动只看到旧数据（历史行不代表当前新增）
- 排查：
  - 看 `daemon.log` 是否持续出现 `Link Rate: ...`
  - 校验换算：`GB/s * 1000 = MB/s`

### 6.3 表面现象：发送 signal 失败（No such process）
- 典型日志：`errno=3 (No such process)`
- 原因：
  - `probe.pid` 过期或上下文不一致
  - probe 已退出（启动竞态、被信号提前打死）
- 排查：
  - `cat logs/probe.pid`
  - `kill -0 <pid>`
  - `pgrep -af '^/root/hostdiagv2pu_diagv3/build/memcpy_benchmark$'`

### 6.4 表面现象：daemon 发了多次，probe 只跑一轮
- 原因：
  - `SIGUSR1` 不是实时队列信号，会合并
  - probe 内部触发标志在一轮完成后清零，忙时多信号可能丢并
- 影响：
  - “多发单触发”是可出现的，不等于 daemon 没发

### 6.5 表面现象：启动脚本提示 `User defined signal 1`
- 原因：
  - probe 刚起时被过早打到 `SIGUSR1`
- 规避：
  - 启动脚本先等待 probe ready，再拉起后续链路（已在脚本中处理）

---

## 7. 快速自检清单（5步）

1) 三进程是否都在  
```bash
pgrep -af '^/root/hostdiagv2pu_diagv3/build/memcpy_benchmark$|trace_memcpy_numa.py|/root/hostdiagv2/npu_adaptive_daemon'
```

2) raw 是否在增长  
```bash
wc -l /root/hostdiagv2/logs/aclrtMemcpy_numa_raw.log
```

3) 聚合是否在增长  
```bash
wc -l /root/hostdiagv2/aclrtMemcpy_numa_trace.log
```

4) daemon 是否在做判定  
```bash
tail -n 50 /root/hostdiagv2/logs/daemon.log
```

5) probe pid 是否可达  
```bash
cat /root/hostdiagv2/logs/probe.pid && kill -0 $(cat /root/hostdiagv2/logs/probe.pid)
```

---

## 8. 工作区文件清单（/root/hostdiagv2）

> 说明：以下清单按“已知用途/待补充”分类。未知项留占位，便于你后续补齐。

### 8.1 已知核心文件
- [trace_memcpy_numa.py](file:///root/hostdiagv2/trace_memcpy_numa.py)  
  用途：eBPF 采集与 src->dst 聚合（核心）
- [npu_adaptive_daemon.cpp](file:///root/hostdiagv2/npu_adaptive_daemon.cpp)  
  用途：守护进程源码（核心）
- [npu_adaptive_daemon](file:///root/hostdiagv2/npu_adaptive_daemon)  
  用途：守护进程可执行文件
- [start_monitor_stack.sh](file:///root/hostdiagv2/start_monitor_stack.sh)  
  用途：一键拉起
- [stop_monitor_stack.sh](file:///root/hostdiagv2/stop_monitor_stack.sh)  
  用途：一键停止
- [logs](file:///root/hostdiagv2/logs)  
  用途：运行日志与 pid 文件目录
- [aclrtMemcpy_numa_trace.log](file:///root/hostdiagv2/aclrtMemcpy_numa_trace.log)  
  用途：聚合输出（daemon 当前监控输入）

### 8.2 待补充说明（基本不会再用）
- [monitor_resource.py](file:///root/hostdiagv2/monitor_resource.py)  
  用途：寒假期间，用于监控监控器的资源使用情况，包括内存和CPU占用率
- [plot_resource.py](file:///root/hostdiagv2/plot_resource.py)  
  用途：寒假期间，用于绘制监控器资源使用情况的图表
- [run_benchmark.sh](file:///root/hostdiagv2/run_benchmark.sh)  
  用途：寒假期间，当时用于运行在大模型背景流下的监控器，一个是监控器+大模型，一个是单纯大模型
- [benchmark.log](file:///root/hostdiagv2/benchmark.log)  
  用途：run_benchmark.sh这个脚本的日志输出
- [cpp_benchmark_resource.csv](file:///root/hostdiagv2/cpp_benchmark_resource.csv)  
  用途：run_benchmark.sh这个脚本中，监控器+大模型的资源使用情况
- [trace_output.log](file:///root/hostdiagv2/trace_output.log)  
  用途：记不清，无所谓的文件
- [trace_resource.csv](file:///root/hostdiagv2/trace_resource.csv)  
  用途：也是无用
- [test_methods_summary.md](file:///root/hostdiagv2/test_methods_summary.md)  
  用途：开始的一版md文件
- [__pycache__](file:///root/hostdiagv2/__pycache__)  
  用途：Python 缓存目录（通常可忽略）

---

## 9. 可维护性建议（后续可做）
- 给 daemon 增加“状态输出模式”，每 N 秒打印当前窗口决策摘要
- 给 start 脚本增加“启动后自检失败自动重拉起”
- 为聚合输出定义稳定 schema 版本号，避免后续字段变化引发兼容问题
- 针对 `aclrtMemcpyAsync` 增加采集（若业务路径确实使用 async）

