# D8: P0.4-R 故障注入重跑 Runbook

**实验目标**: 将故障检测 recall/precision 从 ~48% 提升到 >80%

**原版问题**: budget=2 probes/s 太低 + 注入与训练错峰 → 大量注入窗口内探针未观测到竞争

**解决方法**: 提高探针频率 + 增强注入强度 + 双向竞争

**所需设备**: bms-9002 (Ascend 910A × 8)

---

## 第一步: 启动 GLM-6B 训练 + FlowGap 探针 (预算提高到 5 probes/s)

在 bms-9002 真机上执行。以下命令需要两台终端同时运行:

### 终端 1: 启动训练

```bash
cd /root/mindformers
bash run_distribute.sh \
  "/root/mindformers/mindformers/hccl_8p_01234567_192.168.39.155.json" \
  ../configs/glm/run_glm_6b_finetune.yaml '[0,8]' finetune
```

### 终端 2: 启动 eBPF tracer + FlowGap 在线探针

```bash
# 激活 conda 环境
source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37

cd /root/FlowGap-work/FlowGap-paper/code

# 1. 启动 eBPF tracer (后台)
python ebpf_monitor/trace_memcpy_numa.py --min-size 64 > ../logs/p0.4_round2_raw.log 2>&1 &
TRACER_PID=$!
echo "eBPF tracer PID: $TRACER_PID"

# 2. 等待 warmup (训练稳定后开始 — 约 3 分钟后)
sleep 200

# 3. 启动 FlowGap 在线探针 (budget 从 2 提高到 5 probes/s)
PYTHONPATH=.:trace_parser python evaluation/online_loop_timestamped.py \
  --trace-log ../data/collected/p0.4_raw.log \
  --probe-policy flowgap_predictive \
  --predictor-model-path ../models/gbdt_pass1.pkl \
  --budget-per-sec 5 \
  | tee ../logs/p0.4_round2_probe_ts.log
```

**关键参数对比**:

| 参数 | 原版 (P0.4 v1) | 新版 (v2) | 影响 |
|------|:-----------:|:---------:|------|
| `--budget-per-sec` | 2 | **5** | 2.5× 探针频率 → 更多 BW 探针覆盖 |
| 注入 direction | D2H | **BOTH** | 覆盖 H2D+D2H, 确保与训练真实竞争 |
| 注入 interval-ms | 20 | **1–2** | 10–20× 注入密度 → 训练频繁受扰 → 探针可观测到竞争 |

---

## 第二步: 故障注入 (训练进行约 5 分钟后)

```bash
cd /root/FlowGap-work/FlowGap-paper
source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37

# 启动双向带宽竞争 (持续 300s)
python scripts/inject_bandwidth_contention_v2.py \
  --size-mb 128 \
  --interval-ms 2 \
  --duration 300 \
  --direction BOTH
```

---

## 第三步: 停止采集

注入结束后,等待约 2 分钟恢复期,然后:

```bash
# 终端 2: Ctrl+C 停止 online_loop

# 停 eBPF tracer
kill $TRACER_PID 2>/dev/null
```

---

## 第四步: 分析结果

```bash
cd /root/FlowGap-work/FlowGap-paper/code
source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37

# 运行检测分析
python evaluation/run_p0.4_fault_detection.py \
  --probe-log ../logs/p0.4_round2_probe_ts.log \
  --fault-start <注入开始时间Unix秒> \
  --fault-end <注入结束时间Unix秒> \
  --threshold 0.7 \
  --detect-window 3
```

> 注入开始/结束时间可以从探针日志中查找带宽首次/末次下降的时间戳,或从 `inject_bandwidth_contention_v2.py` 的输出中获取

---

## 预判: 新参数为何能提升 recall/precision

| 问题 | 原版 | 新版 | 理论改善 |
|------|------|------|:---:|
| 训练带宽中位数 0.79 GB/s | 注入器 10ms 间隔 → 12.8 GB/s → 训练大多处于计算 | 2ms 间隔 → ~64 GB/s → 不管训练在计算还是通信,链路都拥堵 | +15-20pp |
| 探针/注入错峰 | budget=2/s → 约每 0.5s 1 probe | budget=5/s + BOTH direction → 每 0.2s 1 probe × 双方向 | +10-15pp |
| H2D 未覆盖 | 仅 D2H 方向注入 | BOTH → 两个方向同时竞争 | +5-10pp |

---

## 如果仍然不到 80%

1. **检查日志时序**: 确认探针与注入时间重叠是否充分
2. **提高 budget 到 10**: `--budget-per-sec 10` (可导致轻微开销,但仍 <0.2%)
3. **缩短注入 interval 到 1ms**: `--interval-ms 1` (极端压力测试)
4. **备用方案 D9**: 降级为 Discussion 中 1–2 句 preliminary observation
