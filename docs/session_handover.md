# FlowGap 项目工作总结与交接

## 一、已完成的工作

### 1. 实验脚本开发与执行 (P0 系列)

#### ✅ P0.1 - 策略对比实验
- **脚本**: `/root/FlowGap-work/FlowGap-paper/code/evaluation/run_p0.1_policy_comparison.py`
- **结果**: `/root/FlowGap-work/FlowGap-paper/code/results/p0.1_v2_probe_coverage/`
- **关键发现**:
  - flowgap 是唯一同时做到 **0% 不安全率 + 27.8% 带宽探针** 的策略
  - random 策略修正为真随机后,不安全率 45.8% (符合预期)
- **指标**: 安全率、不安全率、BW%、开销%、路径覆盖

#### ✅ P0.2.1 - 跨 pass 验证
- **脚本**: `/root/FlowGap-work/FlowGap-paper/code/evaluation/run_p0.2.1_cross_pass_validation.py`
- **结果**: `/root/FlowGap-work/FlowGap-paper/code/results/p0.2.1_cross_pass/`
- **关键发现**:
  - Pass 1 模型在 Pass 2 上: Precision 96.4%, FSR 1.2%~1.5%
  - 500µs: Precision 96.47%, Recall 96.08%, FSR 1.5%
  - 5.1ms: Precision 96.36%, Recall 94.25%, FSR 1.23%
- **论文价值**: 证明模型跨训练迭代的泛化能力

#### ✅ P0.2.2 - 校准评估
- **脚本**: `/root/FlowGap-work/FlowGap-paper/code/evaluation/run_p0.2.2_calibration.py`
- **结果**: `/root/FlowGap-work/FlowGap-paper/code/results/p0.2.2_calibration/`
- **关键发现**:
  - ECE < 0.02 (远低于 0.05 良好阈值)
  - 500µs: 预测 31.14% vs 实际 29.95% (仅差 1.2%)
  - 5.1ms: 预测 26.74% vs 实际 25.74% (仅差 1.0%)
- **论文价值**: 证明概率预测可靠,可直接用于决策

#### ✅ P0.3 - 训练开销测量
- **脚本**: `/root/FlowGap-work/FlowGap-paper/code/evaluation/run_p0.3_training_overhead.py`
- **结果**: `/root/FlowGap-work/FlowGap-paper/code/results/p0.3_training_overhead/`
- **关键发现**:
  - **开销 0.0643%** (488 次探针,总时间 0.772 秒 / 1200 秒训练)
  - LAT 探针: 385 次,平均 121 µs
  - BW 探针: 103 次,平均 7042 µs (7ms),测得 19.3 GB/s
- **方法**: 基于现有日志估算 (方案 A),不需重新训练
- **论文价值**: 证明极低开销,<< 1%

### 2. 代码修复与优化

#### Python 3.7 兼容性修复
- **问题**: MindSpore 要求 Python 3.7,不支持新语法
- **修复**:
  - `trace_parser/schema.py`: 移除 `@dataclass(slots=True)` 中的 `slots=True` (4 处)
  - `gap_predictor/schema.py`: 同上
  - `evaluation/run_p0.1_policy_comparison.py`: `list[type]` → `List[type]`

#### random 策略修正
- **问题**: random 策略实现错误,检查间隙大小后选探针 (实质是"随机+自适应")
- **修复**: `scheduler_replay/policies.py` - 改为真随机,不看间隙大小
- **验证**: `scheduler_replay/test_replay.py` - 更新测试用例

#### online_loop.py 性能优化
- **问题**: `--once` 模式用 tail-poll 逻辑,163K 事件处理 10 分钟卡住
- **修复**: 添加 `_process_full_file()` 方法,一次性读全文件 → parse → 按时间处理
- **效果**: 处理时间从 10 分钟降至 3 秒

### 3. 实验数据与日志

#### 现有数据
- `data/collected/pass1_raw.log` (21M, 备份)
- `data/collected/pass2_raw.log` (22M) — 主要分析数据
- `data/collected/pass2_agg.log` (19M)
- `data/processed/burst_gap_events.parquet` (16166 行, Pass 1)
- `data/processed/burst_gap_events_pass2.parquet` (15945 行, Pass 2)
- `logs/probe_live.log` (19K) — 488 次探针执行记录
- `models/gbdt_pass1.pkl` (879 KB) — 8-horizon GBDT 模型

#### 实验结果汇总
```
results/
├── p0.1_v1_simple_metric/    # 早期版本(保留)
├── p0.1_v2_probe_coverage/   # 最终版本(有意义指标)
├── p0.2.1_cross_pass/        # 跨pass验证
├── p0.2.2_calibration/       # 校准评估
└── p0.3_training_overhead/   # 训练开销
```

---

## 二、未完成的工作

### P0 实验 (1/4 未完成)

#### ⏳ P0.4 - 故障注入实验
- **目标**: 证明 FlowGap 能检测链路故障
- **方法**: 训练中限流一条 HCCS 链路,验证探针检测到带宽下降
- **需求**: 服务器 1-2 小时,手动故障注入脚本
- **产出**: 检测延迟、召回率、带宽 time series

### P1 实验 (增强说服力,可选)

#### P1.1 - 特征消融
- **目标**: 哪些特征最重要
- **方法**: 去掉 gap stats/burst stats/path identity 等特征组,看精度降幅
- **需求**: 本地可做,30 分钟
- **产出**: RQ3 消融表

#### P1.2 - 第二负载验证
- **目标**: 证明通用性
- **方法**: 不同 batch size 或不同模型跑一轮训练
- **需求**: 服务器 2 小时
- **产出**: 跨负载预测精度表

#### P1.3 - eBPF 开销测量
- **目标**: 量化 eBPF trace 本身的开销
- **方法**: 训练期间 top/perf 采样,对比无 tracer 和有 tracer
- **需求**: 可复用已有训练数据
- **产出**: CPU 开销 %

#### P1.4 - 参数敏感性
- **目标**: 置信度阈值、probe budget、window size 的影响
- **方法**: 扫参数,看安全率变化
- **需求**: 本地可做,离线回放
- **产出**: 参数-安全率曲线

### 可视化与文档

#### 需要生成的图表
1. **P0.1**: 7 策略对比柱状图 (安全率、BW%、开销)
2. **P0.2**: 可靠性曲线 (ECE calibration plot)
3. **P0.3**: 探针开销饼图 (LAT vs BW 占比)
4. **整体**: 系统架构图 (eBPF → Parser → GBDT → Scheduler → Executor)

#### 文献综述
- **相关工作梳理**: 网络监控、主动探针、训练性能分析
- **对比分析**: FlowGap vs HostDiagV2 / 周期性探针 / 被动监控
- **需要**: WebSearch 搜索论文 + 整理 Related Work 大纲

---

## 三、关键文件索引

### 核心代码模块
```
code/
├── trace_parser/          # eBPF日志 → 间隙时间线
├── gap_predictor/         # GBDT特征工程+训练
├── probe_scheduler/       # 7种策略+在线循环
├── scheduler_replay/      # 离线回放评估
├── probe_executor/        # AscendCL探针封装
└── evaluation/            # P0/P1实验脚本
    ├── run_p0.1_policy_comparison.py ✅
    ├── run_p0.2.1_cross_pass_validation.py ✅
    ├── run_p0.2.2_calibration.py ✅
    └── run_p0.3_training_overhead.py ✅
```

### 关键配置文件
- `docs/experiment_checklist.md` — 实验待办清单
- `docs/skill_usage_policy.md` — Skill 使用规则
- `scripts/collect_glm6b_trace.sh` — 训练+eBPF采集脚本

### Scientific Agent Skills
- **位置**: `third_party/scientific-agent-skills/skills/` (142 个 skills)
- **已安装**: `.agent/skills/` (14 个核心 skills)
  - scientific-visualization
  - literature-review
  - statistical-analysis
  - exploratory-data-analysis
  - scientific-writing
  - peer-review
  - 等
- **状态**: 未在当前会话加载,需要重启会话识别

---

## 四、技术要点与注意事项

### 1. Python 环境
- **MindSpore**: 需要 Python 3.7 + conda env `mindspore_py37`
- **FlowGap 代码**: 需要 Python 3.7 兼容,避免 3.10+ 语法

### 2. 实验复现
所有 P0 实验都基于**现有数据**,不需要重新训练:
```bash
cd /root/FlowGap-work/FlowGap-paper/code
python evaluation/run_p0.1_policy_comparison.py  # ✅ 已运行
python evaluation/run_p0.2.1_cross_pass_validation.py  # ✅ 已运行
python evaluation/run_p0.2.2_calibration.py  # ✅ 已运行
python evaluation/run_p0.3_training_overhead.py  # ✅ 已运行
```

### 3. 结果版本控制
- P0.1 有 v1 (simple metric) 和 v2 (probe coverage) 两个版本
- v1 保留在 `results/p0.1_v1_simple_metric/`,未覆盖
- v2 是最终版本,用于论文

### 4. 关键设计决策
- **GBDT vs DNN**: 数据量小 (16K),GBDT 足够,可解释性好
- **8 个 horizon**: 对应 3 种探针类型 (TINY 50µs, NORMAL 500µs, BW 5.1ms)
- **安全优先**: 高置信度阈值,宁可不放探针也不干扰训练
- **flowgap 平衡点**: 27.8% BW + 0% 不安全

---

## 五、下一步建议

### 立即可做 (不需要服务器)
1. **可视化**: 用 matplotlib 生成 P0.1-P0.3 图表
2. **文献综述**: WebSearch 搜索相关工作并整理
3. **P1.1 特征消融**: 本地离线分析
4. **P1.4 参数敏感性**: 本地离线回放

### 需要服务器
1. **P0.4 故障注入** (必需,论文核心卖点)
2. **P1.2 第二负载** (增强通用性)

### 论文撰写
- **Results 章节**: 基于 P0.1-P0.3 结果
- **Evaluation 章节**: 补充 P0.4 后完整
- **Related Work**: 需要文献调研

---

## 六、会话交接清单

### 环境信息
- **工作目录**: `/root/FlowGap-work/FlowGap-paper`
- **Python 环境**: Python 3.7 (mindspore_py37)
- **Skills 目录**: `.agent/skills/` (14 个 skills,未加载到当前会话)

### 待验证事项
- 重启会话后,skills 是否能正常加载
- scientific-visualization / literature-review 是否可用
- 如果 skills 仍不可用,用标准 Python 工具替代

### 优先任务
1. 验证 skills 加载
2. 生成 P0.1-P0.3 结果图表
3. 梳理相关工作 (Related Work 大纲)
4. 准备 P0.4 故障注入实验方案

---

## 七、快速参考命令

```bash
# 切换到项目目录
cd /root/FlowGap-work/FlowGap-paper

# 查看实验结果
ls -lh code/results/

# 查看已安装 skills
ls .agent/skills/

# 激活 MindSpore 环境
conda activate mindspore_py37

# 运行实验 (示例)
cd code
python evaluation/run_p0.1_policy_comparison.py
```

---

## 八、P0 实验结果摘要

### P0.1 - 策略对比 (7 种策略)

| 策略 | 安全率 | 不安全率 | BW% | 开销% | 评价 |
|------|--------|----------|-----|-------|------|
| no_probing | 100% | 0% | 0% | 0% | Baseline |
| fixed_interval | 100% | 0% | 0% | 0.64% | 只放 TINY 探针 |
| random | 54.2% | 45.8% | 33.1% | 1.31% | 真随机,不安全 |
| threshold | 100% | 0% | 0% | 0.13% | 保守,无 BW 探针 |
| ewma_only | 100% | 0% | 0% | 0.13% | 同 threshold |
| **flowgap** | **100%** | **0%** | **27.8%** | **1.07%** | **唯一平衡** |
| oracle | 100% | 0% | 29.8% | 1.14% | 理论上界 |

### P0.2.1 - 跨 Pass 验证

| Horizon | Precision | Recall | FSR | Brier |
|---------|-----------|--------|-----|-------|
| 50µs (TINY) | 100% | 100% | 0% | 0.0000 |
| 500µs (NORMAL) | 96.47% | 96.08% | 1.5% | 0.0172 |
| 5.1ms (BW) | 96.36% | 94.25% | 1.23% | 0.0177 |

### P0.2.2 - 校准评估

| Horizon | ECE | Brier | Avg Conf | Avg Acc |
|---------|-----|-------|----------|---------|
| 50µs (TINY) | 0.0000 | 0.0000 | 1.0000 | 1.0000 |
| 500µs (NORMAL) | 0.0183 | 0.0172 | 0.3114 | 0.2995 |
| 5.1ms (BW) | 0.0179 | 0.0177 | 0.2674 | 0.2574 |

### P0.3 - 训练开销

| 指标 | 数值 |
|------|------|
| 训练时长 | 1200 秒 (20 分钟) |
| 探针总数 | 488 次 |
| LAT 探针 | 385 次,平均 121 µs |
| BW 探针 | 103 次,平均 7042 µs |
| 探针总时间 | 0.772 秒 |
| **开销百分比** | **0.0643%** |

---

**交接完成。重启会话后,优先验证 skills 加载,然后继续可视化和文献综述任务。**
