#!/usr/bin/env bash
# P0.4 一键启动脚本 — 支持 SSH 断开后继续运行
#
# 用法:
#   bash scripts/run_p0.4.sh start    # 启动训练+eBPF+探针
#   bash scripts/run_p0.4.sh inject   # 注入故障（训练5-10分钟后执行）
#   bash scripts/run_p0.4.sh stop     # 停止所有进程
#   bash scripts/run_p0.4.sh status   # 查看日志
#   bash scripts/run_p0.4.sh analyze  # 分析结果

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
PID_INJECT="$LOGS/p0.4_inject.pid"

mkdir -p "$LOGS" "$DATA"

activate_conda() {
    source /root/anaconda3/etc/profile.d/conda.sh
    conda activate mindspore_py37
}

cmd_start() {
    echo "=== P0.4 启动 ==="

    # 1. eBPF tracer
    echo "[1/3] 启动 eBPF tracer..."
    nohup /usr/bin/python3 "$REF_REPO/src/trace_memcpy_numa.py" \
        --min-size 1000 \
        --output "$DATA/p0.4_raw.log" \
        --window-ms 100 \
        > "$LOGS/p0.4_ebpf.log" 2>&1 &
    echo $! > "$PID_TRACER"
    echo "  PID=$(cat $PID_TRACER), 等待3秒让uprobes附加..."
    sleep 3
    if ! kill -0 "$(cat $PID_TRACER)" 2>/dev/null; then
        echo "  ERROR: tracer 启动失败，查看 $LOGS/p0.4_ebpf.log"
        exit 1
    fi
    echo "  OK"

    # 2. 探针循环
    echo "[2/3] 启动探针循环..."
    nohup bash -c "
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
    echo "  PID=$(cat $PID_PROBE)"
    echo "  OK"

    # 3. 训练
    echo "[3/3] 启动 GLM-6B 训练..."
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

    echo ""
    echo "=== 全部启动完成 ==="
    echo "查看探针日志:  tail -f $LOGS/p0.4_probe.log"
    echo "查看训练日志:  tail -f $LOGS/p0.4_train.log"
    echo ""
    echo "5-10分钟后执行注入故障:"
    echo "  bash scripts/run_p0.4.sh inject"
}

cmd_inject() {
    echo "=== 注入带宽竞争故障 ==="
    date +"%Y-%m-%d %H:%M:%S" | tee /tmp/p0.4_fault_start.txt
    echo "  注入时间已记录: /tmp/p0.4_fault_start.txt"

    nohup bash -c "
        source /root/anaconda3/etc/profile.d/conda.sh
        conda activate mindspore_py37
        cd $REPO
        python scripts/inject_bandwidth_contention_v2.py \
            --device 0 --interval-ms 5 --duration 180 --direction D2H
        date +\"%Y-%m-%d %H:%M:%S\" > /tmp/p0.4_fault_end.txt
        echo 'fault ended' >> /tmp/p0.4_fault_end.txt
    " > "$LOGS/p0.4_inject.log" 2>&1 &
    echo $! > "$PID_INJECT"
    echo "  注入进程 PID=$(cat $PID_INJECT)"
    echo "  注入持续 180 秒，自动结束"
    echo "  查看进度: tail -f $LOGS/p0.4_inject.log"
}

cmd_stop() {
    echo "=== 停止所有进程 ==="
    for pidfile in "$PID_TRACER" "$PID_PROBE" "$PID_TRAIN" "$PID_INJECT"; do
        if [ -f "$pidfile" ]; then
            pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" && echo "  killed PID=$pid ($(basename $pidfile))"
            else
                echo "  已停止: PID=$pid ($(basename $pidfile))"
            fi
        fi
    done
    echo "  记录结束时间..."
    date +"%Y-%m-%d %H:%M:%S" > /tmp/p0.4_fault_end.txt
    echo "Done"
}

cmd_status() {
    echo "=== P0.4 状态 ==="
    for pidfile in "$PID_TRACER" "$PID_PROBE" "$PID_TRAIN" "$PID_INJECT"; do
        name=$(basename "$pidfile" .pid)
        if [ -f "$pidfile" ]; then
            pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                echo "  RUNNING: $name (PID=$pid)"
            else
                echo "  STOPPED: $name (PID=$pid)"
            fi
        else
            echo "  NOT STARTED: $name"
        fi
    done
    echo ""
    echo "--- 最新探针日志 (tail -5) ---"
    tail -5 "$LOGS/p0.4_probe.log" 2>/dev/null || echo "  (无日志)"
}

cmd_analyze() {
    echo "=== P0.4 分析 ==="
    if [ ! -f /tmp/p0.4_fault_start.txt ]; then
        echo "ERROR: 未找到故障时间 /tmp/p0.4_fault_start.txt"
        exit 1
    fi

    FAULT_START=$(date -d "$(cat /tmp/p0.4_fault_start.txt)" +%s)
    FAULT_END=""
    if [ -f /tmp/p0.4_fault_end.txt ]; then
        FAULT_END=$(date -d "$(head -1 /tmp/p0.4_fault_end.txt)" +%s)
    fi

    source /root/anaconda3/etc/profile.d/conda.sh
    conda activate mindspore_py37
    cd "$CODE"

    if [ -n "$FAULT_END" ]; then
        python evaluation/run_p0.4_fault_detection.py \
            --probe-log "$LOGS/p0.4_probe.log" \
            --fault-start "$FAULT_START" \
            --fault-end "$FAULT_END"
    else
        python evaluation/run_p0.4_fault_detection.py \
            --probe-log "$LOGS/p0.4_probe.log" \
            --fault-start "$FAULT_START"
    fi
}

case "${1:-}" in
    start)   cmd_start ;;
    inject)  cmd_inject ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    analyze) cmd_analyze ;;
    *)
        echo "用法: bash scripts/run_p0.4.sh {start|inject|stop|status|analyze}"
        exit 1
        ;;
esac
