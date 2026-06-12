#!/usr/bin/env bash
# ============================================================================
# collect_glm6b_pass2.sh — Single GLM-6B trace collection run
#
# Uses code/ebpf_monitor/trace_memcpy_numa.py (NNAE-aware).
# Does NOT modify /root/FlowGap-work/reference_repo/.
#
# Output: data/collected/pass2_raw.log, pass2_agg.log, pass2_ebpf.log
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

PASS_NAME="pass2"

# ---- cleanup ----
pkill -9 -f "[t]race_memcpy_numa" 2>/dev/null || true
pkill -9 -f "[r]un_mindformer.py" 2>/dev/null || true
echo "Waiting 15s for HCCL..."
sleep 15

# ---- clean output ----
rm -rf /root/mindformers/output/* 2>/dev/null || true

# ---- start tracer ----
echo "[${PASS_NAME}] Starting eBPF tracer..."
/usr/bin/python3 -u "$TRACE_SCRIPT" \
    --min-size 1000 \
    --output "$OUT_DIR/${PASS_NAME}_raw.log" \
    --window-ms 100 \
    --agg-output "$OUT_DIR/${PASS_NAME}_agg.log" \
    > "$OUT_DIR/${PASS_NAME}_ebpf.log" 2>&1 &
TRACER_PID=$!
echo "[${PASS_NAME}] Tracer PID = $TRACER_PID"

# Wait for BPF compilation + library resolution (aarch64 without BTF takes 15-30s)
sleep 25
LIB=""
for i in $(seq 1 6); do
    if ! kill -0 "$TRACER_PID" 2>/dev/null; then
        echo "[${PASS_NAME}] FATAL: Tracer exited during startup."
        tail -20 "$OUT_DIR/${PASS_NAME}_ebpf.log"
        exit 1
    fi
    LIB=$(grep "nnae" "$OUT_DIR/${PASS_NAME}_ebpf.log" 2>/dev/null || echo "")
    if [ -n "$LIB" ]; then
        break
    fi
    sleep 5
done

if [ -z "$LIB" ]; then
    echo "[${PASS_NAME}] FATAL: Tracer NOT using NNAE library after 55s."
    kill -9 "$TRACER_PID" 2>/dev/null
    tail -10 "$OUT_DIR/${PASS_NAME}_ebpf.log"
    exit 1
fi
echo "[${PASS_NAME}] Library OK: $(grep 'Using AscendCL' "$OUT_DIR/${PASS_NAME}_ebpf.log")"

# ---- start training ----
echo "[${PASS_NAME}] Starting GLM-6B training..."
cd "$TRAIN_DIR"
eval "$TRAIN_CMD" &
TRAIN_PID=$!
echo "[${PASS_NAME}] Training PID = $TRAIN_PID"

# ---- wait for completion ----
echo "[${PASS_NAME}] Waiting for training..."
sleep 240  # 4 min warmup — training init takes ~15 min, we give it 4 before checking

STEP_SEEN=0
while true; do
    RUNNING=$(ps aux | grep "[r]un_mindformer.py" | grep -v grep | wc -l)
    STEP=$(grep "step:" /root/mindformers/output/log/rank_0/mindformer.log 2>/dev/null | tail -1 || echo "")
    if [ -n "$STEP" ]; then
        STEP_SEEN=1
        echo "  [${PASS_NAME}] $STEP"
    fi
    if [ "$RUNNING" -eq 0 ]; then
        if [ "$STEP_SEEN" -eq 0 ]; then
            echo "[${PASS_NAME}] FATAL: Training exited with no steps."
            tail -5 /root/mindformers/output/log/rank_0/info.log 2>/dev/null | grep -i error || true
            kill -9 "$TRACER_PID" 2>/dev/null
            exit 1
        fi
        echo "[${PASS_NAME}] Training finished."
        break
    fi
    sleep 30
done

# ---- stop tracer ----
echo "[${PASS_NAME}] Stopping tracer..."
kill -SIGINT "$TRACER_PID" 2>/dev/null || true
sleep 2
kill -0 "$TRACER_PID" 2>/dev/null && kill -9 "$TRACER_PID" 2>/dev/null || true
wait "$TRACER_PID" 2>/dev/null || true

RAW=$(wc -l < "$OUT_DIR/${PASS_NAME}_raw.log" 2>/dev/null || echo 0)
AGG=$(wc -l < "$OUT_DIR/${PASS_NAME}_agg.log" 2>/dev/null || echo 0)
echo "[${PASS_NAME}] Done. Raw: $RAW lines, Agg: $AGG lines"
echo "[${PASS_NAME}] Finished at $(date)"
ls -lh "$OUT_DIR"/${PASS_NAME}_*.log
