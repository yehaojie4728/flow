#!/usr/bin/env bash
# ============================================================================
# collect_glm6b_trace.sh — Run GLM-6B finetuning + eBPF trace, 2 passes
#
# Phase 1 only (training WITH tracing). No Phase 2 (without tracing).
# Pass 1 → train predictor. Pass 2 → validation.
# Duration: 20 min per pass. Uses /usr/bin/python3 for bpfcc.
#
# Output: data/collected/trace_glm6b_pass1_raw.log
#         data/collected/trace_glm6b_pass1_agg.log
#         data/collected/trace_glm6b_pass2_raw.log
#         data/collected/trace_glm6b_pass2_agg.log
# ============================================================================

set -euo pipefail

COLLECTOR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"/../..
REPO="/root/FlowGap-work/reference_repo"
TRACE_SCRIPT="$REPO/src/trace_memcpy_numa.py"
TRAIN_DIR="/root/mindformers/scripts"
TRAIN_CMD="bash run_distribute.sh /root/mindformers/mindformers/hccl_8p_01234567_192.168.39.155.json ../configs/glm/run_glm_6b_finetune.yaml '[0,8]' finetune"
OUT_DIR="$COLLECTOR/data/collected"
WAIT_MIN=20

# conda env for MindSpore (Python 3.7 required)
source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37

mkdir -p "$OUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ---------------------------------------------------------------------------
# Helper: run one pass
# ---------------------------------------------------------------------------
run_pass() {
    local pass_name="$1"
    local raw_out="$OUT_DIR/trace_glm6b_${pass_name}_raw.log"
    local agg_out="$OUT_DIR/trace_glm6b_${pass_name}_agg.log"
    local trace_log="$OUT_DIR/trace_glm6b_${pass_name}_collector.log"
    local train_log="$OUT_DIR/trace_glm6b_${pass_name}_training.log"

    echo ""
    echo "======================================================================"
    echo "  FlowGap Trace Collection — ${pass_name}"
    echo "  Start: $(date)"
    echo "  Duration: ${WAIT_MIN} min"
    echo "  Raw output:  $raw_out"
    echo "  Agg output:  $agg_out"
    echo "======================================================================"

    # 1. Start eBPF tracer in background (uses SYSTEM python3 for bpfcc)
    echo "[${pass_name}] Starting eBPF tracer..."
    cd "$REPO"
    /usr/bin/python3 "$TRACE_SCRIPT" \
        --min-size 1000 \
        --output "$raw_out" \
        --window-ms 100 \
        --agg-output "$agg_out" \
        > "$trace_log" 2>&1 &
    TRACE_PID=$!
    echo "[${pass_name}] eBPF PID = $TRACE_PID"

    # Give tracer time to attach uprobes
    sleep 3
    if ! kill -0 "$TRACE_PID" 2>/dev/null; then
        echo "[${pass_name}] FATAL: eBPF tracer failed to start. Check $trace_log"
        tail -30 "$trace_log"
        return 1
    fi
    echo "[${pass_name}] eBPF tracer confirmed running."

    # 2. Clean output directory from previous run
    echo "[${pass_name}] Cleaning /root/mindformers/output/ ..."
    rm -rf /root/mindformers/output/* 2>/dev/null || true
    echo "[${pass_name}] Output directory cleaned."

    # 3. Start GLM-6B training
    echo "[${pass_name}] Starting GLM-6B training..."
    cd "$TRAIN_DIR"
    nohup bash -c "$TRAIN_CMD" > "$train_log" 2>&1 &
    TRAIN_PID=$!
    echo "[${pass_name}] Training PID = $TRAIN_PID"

    # 3. Wait
    WAIT_SEC=$((WAIT_MIN * 60))
    echo "[${pass_name}] Waiting ${WAIT_MIN} min (${WAIT_SEC}s)..."
    for i in $(seq 1 $WAIT_MIN); do
        sleep 60
        echo "  [${pass_name}] ... $i/$WAIT_MIN min elapsed at $(date +%H:%M:%S)"
    done

    # 4. Stop eBPF tracer
    echo "[${pass_name}] Stopping eBPF tracer..."
    kill -SIGINT "$TRACE_PID" 2>/dev/null || true
    sleep 2
    kill -0 "$TRACE_PID" 2>/dev/null && kill -9 "$TRACE_PID" 2>/dev/null || true
    wait "$TRACE_PID" 2>/dev/null || true
    echo "[${pass_name}] eBPF tracer stopped."

    # 5. Stop training
    echo "[${pass_name}] Stopping training..."
    kill "$TRAIN_PID" 2>/dev/null || true
    sleep 2
    kill -0 "$TRAIN_PID" 2>/dev/null && kill -9 "$TRAIN_PID" 2>/dev/null || true
    pkill -f "run_mindformer.py" 2>/dev/null || true
    echo "[${pass_name}] Training stopped."

    # 6. Show what we got
    if [ -f "$raw_out" ]; then
        LINES=$(wc -l < "$raw_out")
        SIZE=$(du -h "$raw_out" | cut -f1)
        echo "[${pass_name}] Raw trace: $LINES lines ($SIZE)"
    else
        echo "[${pass_name}] WARNING: raw trace file not found: $raw_out"
    fi
    if [ -f "$agg_out" ]; then
        LINES=$(wc -l < "$agg_out")
        SIZE=$(du -h "$agg_out" | cut -f1)
        echo "[${pass_name}] Agg trace: $LINES lines ($SIZE)"
    fi

    echo "[${pass_name}] Complete at $(date)"
}

# ---------------------------------------------------------------------------
# Main: run 2 passes
# ---------------------------------------------------------------------------

echo ""
echo "============================================================"
echo " FlowGap GLM-6B Trace Collection"
echo " 2 passes × ${WAIT_MIN} min = ~$((WAIT_MIN * 2)) min total"
echo " Started: $(date)"
echo "============================================================"
echo ""
echo "MindFormers config: ${TRAIN_DIR}/../configs/glm/run_glm_6b_finetune.yaml"
echo "NPU devices: 0-7 (8× Ascend 910B)"
echo "eBPF script:  $TRACE_SCRIPT"
echo "Python:       /usr/bin/python3 (for bpfcc)"
echo "MindSpore:    conda env mindspore_py37"
echo ""

# Clean up any leftover processes from abort
pkill -f "trace_memcpy_numa.py" 2>/dev/null || true
pkill -f "run_mindformer.py" 2>/dev/null || true
sleep 2

# Pass 1 — training set
run_pass "pass1" || { echo "Pass 1 failed, aborting."; exit 1; }

# Brief cooldown
echo ""
echo "Cooldown: 30s before pass 2..."
sleep 30

# Pass 2 — validation set
run_pass "pass2" || { echo "Pass 2 failed, aborting."; exit 1; }

echo ""
echo "============================================================"
echo " FlowGap Trace Collection — DONE"
echo " Finished: $(date)"
echo ""
echo " Files:"
ls -lh "$OUT_DIR"/trace_glm6b_pass*_raw.log 2>/dev/null || echo "  (raw traces missing)"
ls -lh "$OUT_DIR"/trace_glm6b_pass*_agg.log 2>/dev/null || echo "  (agg traces missing)"
echo "============================================================"
