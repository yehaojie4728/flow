# FlowGap 实验待办清单

> 更新日期：2026-06-09  
> 用途：与导师沟通实验计划  
> 基准策略：fixed_interval / random / threshold / ewma_only / oracle（均已实现，在 scheduler_replay 中）  
> 本文方法：flowgap_predictive（GBDT 30 维特征预测 + AscendCL 真实探针执行）

---

## 一、已完成

### 1.1 工程基础

| 组件 | 证明 | 测试 |
|---|---|---|
| eBPF 采集器 | GLM-6B 微调 Pass 1/2 各采集 170K+ memcpy 事件 | 实测 |
| Trace Parser | CSV → FlowEvent → 间隙时间线 | 38 tests |
| Gap Predictor | 30 维特征 + 8-horizon GBDT 生存预测 | RQ1 离线 |
| Scheduler Replay | 7 种策略离线回放 + 13 项指标 | 32 tests |
| Probe Executor | AscendCL ctypes 封装，独立 stream，real NPU | 9 tests（NPU 真机） |
| Online Loop | tail eBPF → 解析 → GBDT 预测 → 执行探针 | 端到端验证 |

### 1.2 已有实验结果

| 结果 | 数值 |
|---|---|
| RQ1 可预测性（GBDT precision @ 250µs-2ms） | 95-97%，FSR < 2% |
| 在线真实验证：GLM-6B 训练全程探针 | 488 次（385 LAT + 103 BW），零错误 |
| 带宽探针吞吐 | avg 19.3 GB/s，范围 14.4-20.8 GB/s |
| 延迟探针 | avg 101 µs，范围 24-167 µs |
| 模型持久化 | gbdt_pass1.pkl（879 KB，8 个 horizon） |

---

## 二、实验待办（按优先级）

### P0：论文必需

| # | 实验 | 做法 | 产出 | 需服务器 |
|---|---|---|---|---|
| **P0.1** | **7 策略对比 — 安全率排名** | `scheduler_replay/compare_policies()` 在 Pass 2 数据上跑 7 种策略 | 安全率/有害率/开销 对比表 | 否 |
| **P0.2** | **预测准确性完整评估** | 跨 pass（Pass 1 训 → Pass 2 测）+ ECE 校准 + Brier 分数 | precision/recall/FSR/ECE/Brier 表 | 否 |
| **P0.3** | **训练开销测量** | 无探针 vs FlowGap 探针两轮训练，比 throughput | 吞吐损失 %、iteration 延迟 | **是**（2 轮训练） |
| **P0.4** | **故障注入 + 检测** | 在训练中间限流一条 HCCS 链路，验证探针检测到带宽下降 | 检测延迟、召回率、带宽 time series | **是**（1 轮训练 + 故障脚本） |

### P1：增强说服力

| # | 实验 | 做法 | 产出 | 需服务器 |
|---|---|---|---|---|
| **P1.1** | **特征消融** | 去掉 gap stats/burst stats/path identity 等组，看精度降幅 | RQ3 消融表 | 否 |
| **P1.2** | **第二负载验证** | 不同 batch size 或不同模型跑一轮，dry-run 验证 | 跨负载预测精度表 | **是**（1 轮训练） |
| **P1.3** | **eBPF 开销测量** | 训练期间 top/perf 采样，比无 tracer 和有 tracer | CPU 开销 % | **是**（可复用已有训练） |
| **P1.4** | **参数敏感性** | 扫 η（置信度阈值）/ probe budget / window size | 参数-安全率曲线 | 否 |

### P2：锦上添花

| # | 实验 | 做法 | 产出 | 需服务器 |
|---|---|---|---|---|
| **P2.1** | **冷启动分析** | 1/5/10/50/100 预热样本 vs precision | 冷启动曲线 | 否 |
| **P2.2** | **在线 drift 分析** | Pass 2 最后 20% 的预测精度 vs 前 80% | drift 曲线 | 否 |
| **P2.3** | **oracle 上界对比** | flowgap vs oracle 的 safe_probing_ratio 差距 | 上界差距 | 否 |

---

## 三、服务器时间估算

| 实验 | 训练轮数 | 每轮时长 | 说明 |
|---|---|---|---|
| P0.3（开销） | 2 | ~100 min | 有探针 / 无探针各一轮 |
| P0.4（故障注入） | 1 | ~100 min | 训练中途手动故障 |
| P1.2（第二负载） | 1 | ~100 min | 不同参数 |
| **合计** | **4 轮** | **~7 小时** | 无需连续，可拆分 |

---

## 四、预期论文贡献

1. **流量可预测性**：证明了 Ascend memcpy 流量的间隙存在可预测的结构，GBDT 在 250µs-2ms horizon 上 precision 达 95-97%
2. **低干扰探针调度**：在 GLM-6B 真实训练中执行了 488 次探针，零干扰、零错误——证明预测式调度可行
3. **基准对比**：flowgap_predictive 在安全率上显著优于 fixed_interval/random/threshold/ewma 等 naive 策略
4. **故障检测**：FlowGap 能实时检测链路带宽下降，延迟低于 X 秒
5. **开销量化**：FlowGap 对训练吞吐的影响 < X%

（X 待实验填充）

---

## 五、下一步行动

**立即开始 P0.1**（不需要服务器，直接跑 scheduler_replay 对比）：
```bash
cd /root/FlowGap-work/FlowGap-paper/code
source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37
PYTHONPATH=.:trace_parser python -c "
from trace_parser.parse_trace import group_by_path, parse_csv
from trace_parser.intervalize import build_timeline
from scheduler_replay.replay import compare_policies
from scheduler_replay.metrics import metrics_table

# Load Pass 2 data
events = parse_csv('../data/collected/pass2_raw.log')
by_path = group_by_path(events)
top4 = sorted(by_path.items(), key=lambda x: -len(x[1]))[:8]

timelines = {}
for pk, evs in top4:
    pid = hash(pk) & 0xFFFF
    busy, gaps = build_timeline(evs, 50_000, 100_000, pid)
    timelines[pid] = (busy, gaps)

print(f'Timelines built: {len(timelines)} paths')
results = compare_policies(timelines)
print()
print(metrics_table(results))
"
```
