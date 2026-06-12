#!/usr/bin/env bash
# ============================================================================
# collect_glm6b_full.sh — 2-pass GLM-6B trace collection (full training runs)
#
# FlowGap edition. Uses code/ebpf_monitor/trace_memcpy_numa.py (NNAE-aware).
# Does NOT modify /root/FlowGap-work/reference_repo/.
#
# Pass 1: full training + tracing → data/collected/pass1_raw.log
# Pass 2: full training + tracing → data/collected/pass2_raw.log
#
# /root/mindformers/output/* is deleted before each pass.
# ============================================================================

set -euo pipefail

COLLECTOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
TRACE_SCRIPT="$COLLECTOR_ROOT/code/ebpf_monitor/trace_memcpy_numa.py"
TRAIN_DIR="/root/mindformers/scripts"
TRAIN_CMD="bash run_distribute.sh /root/mindformers/mindformers/hccl_8p_01234567_192.168.39.155.json ../configs/glm/run_glm_6b_finetune.yaml '[0,8]' finetune"
OUT_DIR="$COLLECTOR_ROOT/data/collected"

source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37

mkdir -p "$OUT_DIR"

# ===========================================================================
run_pass() {
    local pass_name="$1"
    local raw_out="$OUT_DIR/${pass_name}_raw.log"
    local agg_out="$OUT_DIR/${pass_name}_agg.log"

    echo ""
    echo "======================================================================"
    echo "  FlowGap Trace — ${pass_name}"
    echo "  Start: $(date)"
    echo "======================================================================"

    # 1. Clean output
    echo "[${pass_name}] Cleaning /root/mindformers/output/ ..."
    rm -rf /root/mindformers/output/* 2>/dev/null || true
    echo "[${pass_name}] Output cleaned."

    # 2. Start eBPF tracer
    echo "[${pass_name}] Starting eBPF tracer..."
    /usr/bin/python3 -u "$TRACE_SCRIPT" \
        --min-size 1000 \
        --output "$raw_out" \
        --window-ms 100 \
        --agg-output "$agg_out" \
        > "$OUT_DIR/${pass_name}_ebpf.log" 2>&1 &
    TRACER_PID=$!
    echo "[${pass_name}] Tracer PID = $TRACER_PID"

    sleep 3
    if ! kill -0 "$TRACER_PID" 2>/dev/null; then
        echo "[${pass_name}] FATAL: Tracer failed to start."
        tail -20 "$OUT_DIR/${pass_name}_ebpf.log"
        return 1
    fi

    # Verify library path
    local lib_path=$(grep 'Using AscendCL' "$OUT_DIR/${pass_name}_ebpf.log" 2>/dev/null || echo "")
    if [ -z "$lib_path" ]; then
        # Wait a bit more for BPF compilation
        sleep 5
        lib_path=$(grep 'Using AscendCL' "$OUT_DIR/${pass_name}_ebpf.log" 2>/dev/null || echo "")
    fi
    if [ -z "$lib_path" ]; then
        echo "[${pass_name}] FATAL: Tracer failed to resolve AscendCL library."
        tail -20 "$OUT_DIR/${pass_name}_ebpf.log"
        kill -9 "$TRACER_PID" 2>/dev/null || true
        return 1
    fi
    echo "[${pass_name}] Library: $lib_path"

    # 3. Start training (runs to completion — ~76 min for 7162 steps)
    echo "[${pass_name}] Starting GLM-6B training..."
    cd "$TRAIN_DIR"
    eval "$TRAIN_CMD" &
    TRAIN_PID=$!
    echo "[${pass_name}] Training PID = $TRAIN_PID"

    # 4. Wait for training to finish naturally
    echo "[${pass_name}] Waiting for training to complete..."
    local last_step="(not started)"
    local warmup_checks=0
    while true; do
        local running=$(ps aux | grep "[r]un_mindformer.py" | grep -v grep | wc -l)
        local step_line=$(grep "step:" /root/mindformers/output/log/rank_0/mindformer.log 2>/dev/null | tail -1 || echo "")
        if [ -n "$step_line" ] && [ "$step_line" != "$last_step" ]; then
            echo "  [${pass_name}] $step_line"
            last_step="$step_line"
        fi
        if [ "$running" -eq 0 ]; then
            # Check if training EVER started producing steps
            if [ "$last_step" = "(not started)" ]; then
                echo "[${pass_name}] FATAL: Training exited without producing any steps (HCCL error?)."
                tail -20 /root/mindformers/output/log/rank_0/info.log 2>/dev/null | grep -i error || true
                return 1
            fi
            echo "[${pass_name}] All training processes finished."
            break
        fi
        sleep 10
    done
    wait "$TRAIN_PID" 2>/dev/null || true

    # 5. Stop tracer
    echo "[${pass_name}] Stopping tracer..."
    kill -SIGINT "$TRACER_PID" 2>/dev/null || true
    sleep 2
    kill -0 "$TRACER_PID" 2>/dev/null && kill -9 "$TRACER_PID" 2>/dev/null || true
    wait "$TRACER_PID" 2>/dev/null || true

    # 6. Report
    local raw_lines=$(wc -l < "$raw_out" 2>/dev/null || echo 0)
    local agg_lines=$(wc -l < "$agg_out" 2>/dev/null || echo 0)
    echo "[${pass_name}] Done. Raw: $raw_lines lines, Agg: $agg_lines lines"
    echo "[${pass_name}] Finished at $(date)"
}

# ===========================================================================
# Cleanup leftover processes from previous runs
ps aux | grep "[t]race_memcpy_numa" | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true
ps aux | grep "[r]un_mindformer.py" | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true
# HCCL needs 10+ seconds to release device resources — see MindSpore error EJ0001
echo "Waiting 15s for HCCL cleanup..."
sleep 15

echo ""
echo "================================================================"
echo " FlowGap GLM-6B Full Trace Collection"
echo " 2 passes. Each pass: full training run (~76 min for 7162 steps)"
echo " Started: $(date)"
echo "================================================================"

# Pass 1
run_pass "pass1" || { echo "Pass 1 failed."; exit 1; }
echo ""
echo "Cooldown: 30s..."
sleep 30

# Pass 2
run_pass "pass2" || { echo "Pass 2 failed."; exit 1; }

echo ""
echo "================================================================"
echo " FlowGap Trace Collection — DONE"
echo " Finished: $(date)"
echo ""
ls -lh "$OUT_DIR"/pass*_raw.log 2>/dev/null
ls -lh "$OUT_DIR"/pass*_agg.log 2>/dev/null
echo "================================================================"
