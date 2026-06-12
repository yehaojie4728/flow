#!/usr/bin/env bash
# ============================================================================
# run_p0.4_final.sh — P0.4 完整实验（训练 + eBPF + 故障注入）
#
# 用法:
#   bash scripts/run_p0.4_final.sh        # 启动训练+eBPF+故障注入
#   
# 然后在另一个终端手动启动探针循环：
#   cd /root/FlowGap-work/FlowGap-paper/code
#   conda activate mindspore_py37
#   PYTHONPATH=.:trace_parser python probe_scheduler/online_loop.py \
#       --trace-log ../data/collected/p0.4_raw.log \
#       --probe-policy flowgap_predictive \
#       --predictor-model-path ../models/gbdt_pass1.pkl \
#       --budget-per-sec 2 \
#       --timestamp \
#       | tee ../logs/p0.4_probe.log
#
# 输出:
#   - data/collected/p0.4_raw.log（eBPF trace）
#   - logs/p0.4_fault_schedule.log（故障注入日志）
#   - logs/p0.4_train.log（训练日志）
# ============================================================================

set -euo pipefail

REPO="/root/FlowGap-work/FlowGap-paper"
REF_REPO="/root/FlowGap-work/reference_repo"
CODE="$REPO/code"
DATA="$REPO/data/collected"
LOGS="$REPO/logs"
TRAIN_DIR="/root/mindformers/scripts"
HCCL_JSON="/root/mindformers/mindformers/hccl_8p_01234567_192.168.39.155.json"
MODEL="$REPO/models/gbdt_pass1.pkl"

# ============================================================================
# analyze 子命令（直接跳转分析，不执行启动流程）
# ============================================================================
if [ "${1:-}" = "analyze" ]; then
    source /root/anaconda3/etc/profile.d/conda.sh
    conda activate mindspore_py37
    cd "$CODE"
    
    echo ""
    echo "=== P0.4 分析结果 ==="

    # 分析第1次注入
    if [ -f /tmp/p0.4_fault1_start.txt ]; then
        echo ""
        echo "--- 第1次注入 (极限竞争, 1ms BOTH) ---"
        F1_START=$(date -d "$(cat /tmp/p0.4_fault1_start.txt)" +%s)
        F1_END=$(date -d "$(cat /tmp/p0.4_fault1_end.txt)" +%s 2>/dev/null || echo "")
        if [ -n "$F1_END" ]; then
            python evaluation/run_p0.4_fault_detection.py \
                --probe-log "$LOGS/p0.4_probe_ts.log" \
                --fault-start "$F1_START" --fault-end "$F1_END" \
                --baseline-end "$F1_START" \
                --threshold 0.7
        else
            echo "  第1次注入尚未结束"
        fi
    else
        echo "  第1次注入尚未开始"
    fi

    # 分析第2次注入
    if [ -f /tmp/p0.4_fault2_start.txt ]; then
        echo ""
        echo "--- 第2次注入 (极限竞争, 1ms BOTH) ---"
        F1_START=$(date -d "$(cat /tmp/p0.4_fault1_start.txt)" +%s)  # 复用第1次开始时间作为基线截止
        F2_START=$(date -d "$(cat /tmp/p0.4_fault2_start.txt)" +%s)
        F2_END=$(date -d "$(cat /tmp/p0.4_fault2_end.txt)" +%s 2>/dev/null || echo "")
        if [ -n "$F2_END" ]; then
            python evaluation/run_p0.4_fault_detection.py \
                --probe-log "$LOGS/p0.4_probe_ts.log" \
                --fault-start "$F2_START" --fault-end "$F2_END" \
                --baseline-end "$F1_START" \
                --threshold 0.7
        else
            echo "  第2次注入尚未结束"
        fi
    else
        echo "  第2次注入尚未开始"
    fi
    
    echo ""
    echo "=== 分析完成 ==="
    echo "  结果目录: $CODE/results/p0.4_fault_detection/"
    exit 0
fi

# ============================================================================
# 正常启动流程
# ============================================================================
source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37
mkdir -p "$LOGS" "$DATA"

# ============================================================================
# 检查 eBPF tracer 是否已在运行
# ============================================================================
echo "=== P0.4 环境检查 ==="
EXISTING_TRACER=$(pgrep -f "trace_memcpy_numa.py.*p0.4_raw.log" || echo "")
if [ -n "$EXISTING_TRACER" ]; then
    echo "  检测到 eBPF tracer 已在运行 (PID=$EXISTING_TRACER)"
    echo "  验证日志..."
    if grep -q "Using AscendCL" "$LOGS/p0.4_ebpf.log" 2>/dev/null; then
        echo "  ✓ 使用现有 tracer"
        TRACER_PID=$EXISTING_TRACER
    else
        echo "  现有 tracer 日志异常，清理并重启..."
        pkill -9 -f "[t]race_memcpy_numa.*p0.4" 2>/dev/null || true
        sleep 3
        EXISTING_TRACER=""
    fi
fi

# 清理其他进程
echo "  清理旧的训练和探针进程..."
pkill -9 -f "[r]un_mindformer.py" 2>/dev/null || true
pkill -9 -f "[o]nline_loop" 2>/dev/null || true
pkill -9 -f "[i]nject_bandwidth" 2>/dev/null || true
echo "  等待 HCCL 清理..."
sleep 15

rm -rf /root/mindformers/output/* 2>/dev/null || true

# ============================================================================
# 1. 启动 eBPF tracer（如果尚未运行）
# ============================================================================
if [ -z "$EXISTING_TRACER" ]; then
    echo ""
    echo "=== [1/4] 启动 eBPF tracer ==="
    /usr/bin/python3 -u "$CODE/ebpf_monitor/trace_memcpy_numa.py" \
        --min-size 1000 \
        --output "$DATA/p0.4_raw.log" \
        --window-ms 100 \
        --agg-output "$DATA/p0.4_raw.log.agg" \
        > "$LOGS/p0.4_ebpf.log" 2>&1 &
    TRACER_PID=$!
    echo "  Tracer PID = $TRACER_PID"
    echo $TRACER_PID > "$LOGS/p0.4_tracer.pid"

    # 等待 BPF 编译和库解析
    echo "  等待 BPF 编译（30秒）..."
    sleep 30

    # 检查 tracer 是否成功挂载
    LIB=""
    for i in $(seq 1 6); do
        if ! kill -0 "$TRACER_PID" 2>/dev/null; then
            echo "  FATAL: Tracer 启动失败"
            tail -20 "$LOGS/p0.4_ebpf.log"
            exit 1
        fi
        LIB=$(grep "Using AscendCL" "$LOGS/p0.4_ebpf.log" 2>/dev/null || echo "")
        if [ -n "$LIB" ]; then
            break
        fi
        sleep 5
    done

    if [ -z "$LIB" ]; then
        echo "  FATAL: Tracer 未找到 AscendCL 库（60秒后）"
        kill -9 "$TRACER_PID" 2>/dev/null
        tail -10 "$LOGS/p0.4_ebpf.log"
        exit 1
    fi
    echo "  ✓ Tracer 就绪: $LIB"
else
    echo ""
    echo "=== [1/4] eBPF tracer 已运行，跳过启动 ==="
fi

# ============================================================================
# 2. 启动训练
# ============================================================================
echo ""
echo "=== [2/4] 启动 GLM-6B 训练 ==="
cd "$TRAIN_DIR"
bash run_distribute.sh "$HCCL_JSON" \
    ../configs/glm/run_glm_6b_finetune.yaml '[0,8]' finetune \
    > "$LOGS/p0.4_train.log" 2>&1 &
TRAIN_PID=$!
echo "  Training PID = $TRAIN_PID"
echo $TRAIN_PID > "$LOGS/p0.4_train.pid"

# ============================================================================
# 3. 启动自动化故障注入（后台运行）
# ============================================================================
echo ""
echo "=== [3/3] 启动自动化故障注入 ==="
echo "  20 分钟后: 第1次注入（极限竞争, 1ms, 10分钟, BOTH）"
echo "  40 分钟后: 恢复正常"
echo "  60 分钟后: 第2次注入（极限竞争, 1ms, 10分钟, BOTH）"
echo "  日志: $LOGS/p0.4_fault_schedule.log"
echo ""

bash -c "
    source /root/anaconda3/etc/profile.d/conda.sh
    conda activate mindspore_py37
    cd $REPO

    echo '[$(date)] 等待 20 分钟建立基线...' >> $LOGS/p0.4_fault_schedule.log
    sleep $((20*60))

    echo '[$(date)] === 第1次注入: 极限竞争 (1ms, 10min, BOTH) ===' | tee -a $LOGS/p0.4_fault_schedule.log
    date +\"%Y-%m-%d %H:%M:%S\" > /tmp/p0.4_fault1_start.txt
    python scripts/inject_bandwidth_contention_v2.py \
        --interval-ms 1 --duration 600 --direction BOTH \
        >> $LOGS/p0.4_fault_schedule.log 2>&1
    date +\"%Y-%m-%d %H:%M:%S\" > /tmp/p0.4_fault1_end.txt
    echo '[$(date)] 第1次注入结束' | tee -a $LOGS/p0.4_fault_schedule.log

    echo '[$(date)] 恢复正常 20 分钟...' >> $LOGS/p0.4_fault_schedule.log
    sleep $((20*60))

    echo '[$(date)] === 第2次注入: 极限竞争 (1ms, 10min, BOTH) ===' | tee -a $LOGS/p0.4_fault_schedule.log
    date +\"%Y-%m-%d %H:%M:%S\" > /tmp/p0.4_fault2_start.txt
    python scripts/inject_bandwidth_contention_v2.py \
        --interval-ms 1 --duration 600 --direction BOTH \
        >> $LOGS/p0.4_fault_schedule.log 2>&1
    date +\"%Y-%m-%d %H:%M:%S\" > /tmp/p0.4_fault2_end.txt
    echo '[$(date)] 第2次注入结束' | tee -a $LOGS/p0.4_fault_schedule.log

    echo '[$(date)] 自动注入任务完成' | tee -a $LOGS/p0.4_fault_schedule.log
" > /dev/null 2>&1 &

AUTO_PID=$!
echo "  Auto-inject PID = $AUTO_PID"
echo $AUTO_PID > "$LOGS/p0.4_auto.pid"

# ============================================================================
# 4. 提示手动启动探针循环
# ============================================================================
echo ""
echo "=== P0.4 后台进程已启动 ==="
echo "  Tracer PID:      $TRACER_PID"
echo "  Training PID:    $TRAIN_PID"
echo "  Auto-inject PID: $AUTO_PID"
echo ""
echo "=== 下一步：在另一个终端手动启动探针循环 ==="
echo ""
echo "  等训练产生初始 trace 后（约5分钟），在新终端执行："
echo ""
echo "    cd /root/FlowGap-work/FlowGap-paper/code"
echo "    conda activate mindspore_py37"
echo "    nohup python -u evaluation/online_loop_timestamped.py \\"
echo "        --trace-log ../data/collected/p0.4_raw.log \\"
echo "        --probe-policy flowgap_predictive \\"
echo "        --predictor-model-path ../models/gbdt_pass1.pkl \\"
echo "        --budget-per-sec 10 \\"
echo "        > ../logs/p0.4_probe_ts.log 2>&1 &"
echo ""
echo "  实时查看："
echo "    tail -f $LOGS/p0.4_ebpf.log           # eBPF trace 数据"
echo "    tail -f $LOGS/p0.4_fault_schedule.log # 故障注入进度"
echo "    tail -f $LOGS/p0.4_train.log          # 训练日志"
echo ""

echo "=== P0.4 脚本完成 ==="
echo "  可以断开此 SSH，后台进程继续运行"
echo "  100 分钟后运行分析: bash scripts/run_p0.4_final.sh analyze"


