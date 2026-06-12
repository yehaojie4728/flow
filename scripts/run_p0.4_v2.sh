#!/usr/bin/env bash
# P0.4 改进版 — 多阶段故障注入
#
# 用法:
#   bash scripts/run_p0.4_v2.sh start        # 启动训练+eBPF+探针
#   bash scripts/run_p0.4_v2.sh auto-inject # 自动化注入（训练20/40/60分钟时）
#   bash scripts/run_p0.4_v2.sh stop         # 停止
#   bash scripts/run_p0.4_v2.sh analyze      # 分析

set -euo pipefail

REPO="/root/FlowGap-work/FlowGap-paper"
REF_REPO="/root/FlowGap-work/reference_repo"
CODE="$REPO/code"
DATA="$REPO/data/collected"
LOGS="$REPO/logs"
TRAIN_DIR="/root/mindformers/scripts"
HCCL_JSON="/root/mindformers/mindformers/hccl_8p_01234567_192.168.39.155.json"
MODEL="$REPO/models/gbdt_pass1.pkl"

PID_TRACER="$LOGS/p0.4_tracer.pid"
PID_PROBE="$LOGS/p0.4_probe.pid"
PID_TRAIN="$LOGS/p0.4_train.pid"
PID_AUTO="$LOGS/p0.4_auto.pid"

FAULT_LOG="$LOGS/p0.4_fault_schedule.log"

mkdir -p "$LOGS" "$DATA"

cmd_start() {
    echo "=== P0.4 启动 (改进版: 多阶段注入) ==="

    # 1. eBPF tracer
    echo "[1/3] 启动 eBPF tracer..."
    nohup /usr/bin/python3 "$REF_REPO/src/trace_memcpy_numa.py" \
        --min-size 1000 \
        --output "$DATA/p0.4_raw.log" \
        --window-ms 100 \
        > "$LOGS/p0.4_ebpf.log" 2>&1 &
    echo $! > "$PID_TRACER"
    echo "  PID=$(cat $PID_TRACER)"
    sleep 3
    echo "  OK"

    # 3. 训练
    echo "[2/3] 启动 GLM-6B 训练（预计100分钟）..."
    rm -rf /root/mindformers/output/* 2>/dev/null || true
    nohup bash -c "
        source /root/anaconda3/etc/profile.d/conda.sh
        conda activate mindspore_py37
        cd $TRAIN_DIR
        bash run_distribute.sh $HCCL_JSON \
            ../configs/glm/run_glm_6b_finetune.yaml '[0,8]' finetune
    " > "$LOGS/p0.4_train.log" 2>&1 &
    echo $! > "$PID_TRAIN"
    echo "  PID=$(cat $PID_TRAIN)"
    echo "  OK"

    # 3. 探针循环（延迟启动，避免与训练 NPU 初始化冲突）
    echo "[3/3] 启动探针循环（等 trace 数据充足后自动启动）..."
    nohup bash -c "
        echo '等待训练产生 memcpy 事件后再初始化探针...'
        # 等 trace 文件有足够数据（训练真正开始后才有大量 memcpy）
        while true; do
            count=\$(wc -l < $DATA/p0.4_raw.log 2>/dev/null || echo 0)
            echo \"当前 trace 行数: \$count\"
            [ \"\$count\" -gt 500 ] && break
            sleep 30
        done
        echo 'trace 数据充足，启动探针循环'
        source /root/anaconda3/etc/profile.d/conda.sh
        conda activate mindspore_py37
        cd $CODE
        PYTHONPATH=.:trace_parser python probe_scheduler/online_loop.py \
            --trace-log $DATA/p0.4_raw.log \
            --probe-policy flowgap_predictive \
            --predictor-model-path $MODEL \
            --budget-per-sec 2 \
            --timestamp
    " > "$LOGS/p0.4_probe.log" 2>&1 &
    echo $! > "$PID_PROBE"
    echo "  PID=$(cat $PID_PROBE) (等待 trace 有 500+ 行后自动启动)"
    echo "  OK"

    echo ""
    echo "=== 全部启动完成 ==="
    echo "查看探针日志:  tail -f $LOGS/p0.4_probe.log"
    echo ""
    echo "启动自动注入（推荐）:"
    echo "  bash scripts/run_p0.4_v2.sh auto-inject &"
    echo ""
    echo "或手动注入:"
    echo "  20分钟后: bash scripts/run_p0.4_v2.sh inject 20 light"
    echo "  60分钟后: bash scripts/run_p0.4_v2.sh inject 5 heavy"
}

cmd_auto_inject() {
    echo "=== 自动化多阶段注入 ==="
    echo "  20分钟: 建立基线"
    echo "  20-25分钟: 轻度拥塞 (interval=20ms)"
    echo "  40分钟: 恢复"
    echo "  60-65分钟: 重度拥塞 (interval=5ms)"
    echo "  日志: $FAULT_LOG"
    echo ""

    nohup bash -c "
        source /root/anaconda3/etc/profile.d/conda.sh
        conda activate mindspore_py37
        cd $REPO

        echo '[$(date)] 等待20分钟建立基线...' >> $FAULT_LOG
        sleep $((20*60))

        echo '[$(date)] === 第1次注入: 轻度拥塞 (20ms, 5分钟) ===' | tee -a $FAULT_LOG
        date +\"%Y-%m-%d %H:%M:%S\" > /tmp/p0.4_fault1_start.txt
        python scripts/inject_bandwidth_contention_v2.py \
            --interval-ms 20 --duration 300 --direction D2H \
            >> $FAULT_LOG 2>&1
        date +\"%Y-%m-%d %H:%M:%S\" > /tmp/p0.4_fault1_end.txt
        echo '[$(date)] 第1次注入结束' | tee -a $FAULT_LOG

        echo '[$(date)] 恢复正常20分钟...' >> $FAULT_LOG
        sleep $((20*60))

        echo '[$(date)] === 第2次注入: 重度拥塞 (5ms, 5分钟) ===' | tee -a $FAULT_LOG
        date +\"%Y-%m-%d %H:%M:%S\" > /tmp/p0.4_fault2_start.txt
        python scripts/inject_bandwidth_contention_v2.py \
            --interval-ms 5 --duration 300 --direction D2H \
            >> $FAULT_LOG 2>&1
        date +\"%Y-%m-%d %H:%M:%S\" > /tmp/p0.4_fault2_end.txt
        echo '[$(date)] 第2次注入结束' | tee -a $FAULT_LOG

        echo '[$(date)] 自动注入任务完成' | tee -a $FAULT_LOG
    " > /dev/null 2>&1 &

    echo $! > "$PID_AUTO"
    echo "  自动注入进程 PID=$(cat $PID_AUTO)"
    echo "  后台运行，SSH断开也会继续"
    echo "  查看进度: tail -f $FAULT_LOG"
}

cmd_inject() {
    local interval="${1:-10}"
    local label="${2:-manual}"
    
    echo "=== 手动注入故障 (interval=${interval}ms, label=$label) ==="
    date +"%Y-%m-%d %H:%M:%S" | tee "/tmp/p0.4_fault_${label}_start.txt"

    source /root/anaconda3/etc/profile.d/conda.sh
    conda activate mindspore_py37
    cd "$REPO"
    
    python scripts/inject_bandwidth_contention_v2.py \
        --device 0 --interval-ms "$interval" --duration 300 --direction D2H

    date +"%Y-%m-%d %H:%M:%S" | tee "/tmp/p0.4_fault_${label}_end.txt"
    echo "Done"
}

cmd_stop() {
    echo "=== 停止所有进程 ==="
    for pidfile in "$PID_TRACER" "$PID_PROBE" "$PID_TRAIN" "$PID_AUTO"; do
        if [ -f "$pidfile" ]; then
            pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" && echo "  killed PID=$pid"
            fi
        fi
    done
    # 停止所有 inject_bandwidth_contention 进程
    pkill -f inject_bandwidth_contention && echo "  killed contention injectors"
    echo "Done"
}

cmd_analyze() {
    echo "=== P0.4 分析 ==="
    
    source /root/anaconda3/etc/profile.d/conda.sh
    conda activate mindspore_py37
    cd "$CODE"

    # 分析第1次注入
    if [ -f /tmp/p0.4_fault1_start.txt ]; then
        echo ""
        echo "--- 第1次注入 (轻度拥塞) ---"
        F1_START=$(date -d "$(cat /tmp/p0.4_fault1_start.txt)" +%s)
        F1_END=$(date -d "$(cat /tmp/p0.4_fault1_end.txt)" +%s 2>/dev/null || echo "")
        if [ -n "$F1_END" ]; then
            python evaluation/run_p0.4_fault_detection.py \
                --probe-log "$LOGS/p0.4_probe.log" \
                --fault-start "$F1_START" --fault-end "$F1_END" \
                --threshold 0.8
        fi
    fi

    # 分析第2次注入
    if [ -f /tmp/p0.4_fault2_start.txt ]; then
        echo ""
        echo "--- 第2次注入 (重度拥塞) ---"
        F2_START=$(date -d "$(cat /tmp/p0.4_fault2_start.txt)" +%s)
        F2_END=$(date -d "$(cat /tmp/p0.4_fault2_end.txt)" +%s 2>/dev/null || echo "")
        if [ -n "$F2_END" ]; then
            python evaluation/run_p0.4_fault_detection.py \
                --probe-log "$LOGS/p0.4_probe.log" \
                --fault-start "$F2_START" --fault-end "$F2_END" \
                --threshold 0.7
        fi
    fi
}

case "${1:-}" in
    start)       cmd_start ;;
    auto-inject) cmd_auto_inject ;;
    inject)      cmd_inject "${2:-10}" "${3:-manual}" ;;
    stop)        cmd_stop ;;
    analyze)     cmd_analyze ;;
    *)
        echo "用法: bash scripts/run_p0.4_v2.sh {start|auto-inject|inject|stop|analyze}"
        exit 1
        ;;
esac
