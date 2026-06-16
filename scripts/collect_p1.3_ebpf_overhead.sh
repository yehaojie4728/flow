#!/usr/bin/env bash
# ============================================================================
# collect_p1.3_ebpf_overhead.sh — Measure eBPF tracer CPU overhead
#
# P1.3: Run GLM-6B training in two phases and sample CPU:
#   Phase A (baseline) : training WITHOUT eBPF tracer
#   Phase B (traced)   : training WITH eBPF tracer
#
# CPU sampling: mpstat (whole-system) + pidstat (tracer process)
# Compares system CPU utilization between the two phases, and reports
# the tracer process's own CPU consumption.
#
# Output: data/collected/p1.3_overhead/
#   - phase_a_mpstat.log     (baseline system CPU samples)
#   - phase_b_mpstat.log     (traced system CPU samples)
#   - phase_b_pidstat.log    (tracer process CPU samples)
#   - phase_a_training.log / phase_b_training.log
#   - phase_b_tracer.log
#   - meta.txt               (timing / config metadata)
# ============================================================================

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
CODE="$REPO_ROOT/code"
# FlowGap edition tracer (includes NNAE 7.0.0 lib fix) — same as run_p0.4_final.sh
TRACE_SCRIPT="$CODE/ebpf_monitor/trace_memcpy_numa.py"
TRAIN_DIR="/root/mindformers/scripts"
HCCL_JSON="/root/mindformers/mindformers/hccl_8p_01234567_192.168.39.155.json"
OUT_DIR="$REPO_ROOT/data/collected/p1.3_overhead"

# GLM-6B distributed finetune launch (same invocation as run_p0.4_final.sh)
TRAIN_CMD="bash run_distribute.sh \"$HCCL_JSON\" ../configs/glm/run_glm_6b_finetune.yaml '[0,8]' finetune"

# Timing (seconds).
# Sampling no longer starts after a fixed warmup. Instead the traced phase waits
# until the eBPF tracer emits its first real record, and the baseline phase reuses
# that measured warmup so both phases sample at the same training maturity.
WARMUP_SEC="${WARMUP_SEC:-180}"          # fallback only (if no measured value)
WARMUP_TIMEOUT="${WARMUP_TIMEOUT:-1800}" # max wait for first eBPF record (30 min)
SAMPLE_SEC="${SAMPLE_SEC:-300}"          # 5 min sampling
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-2}"  # mpstat/pidstat interval

# Set by the traced phase (time from training start to first eBPF record),
# reused by the baseline phase for a fair comparison.
MEASURED_WARMUP=""

source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37

mkdir -p "$OUT_DIR"

cleanup_procs() {
    pkill -9 -f "[t]race_memcpy_numa.py" 2>/dev/null || true
    pkill -9 -f "[r]un_mindformer.py" 2>/dev/null || true
    pkill -9 -f "[r]un_distribute.sh" 2>/dev/null || true
}

# Count real data rows (excludes the CSV header line) in the tracer raw output.
ebpf_record_count() {
    local f="$1"
    [ -f "$f" ] || { echo 0; return; }
    local n
    n=$(wc -l < "$f" 2>/dev/null || echo 0)
    # subtract the 1-line CSV header
    if [ "$n" -gt 0 ]; then echo $(( n - 1 )); else echo 0; fi
}

# ---------------------------------------------------------------------------
# Run one phase. $1 = phase name (a|b), $2 = with_tracer (0|1)
# ---------------------------------------------------------------------------
run_phase() {
    local phase="$1"
    local with_tracer="$2"
    local train_log="$OUT_DIR/phase_${phase}_training.log"
    local mpstat_log="$OUT_DIR/phase_${phase}_mpstat.log"
    local tracer_log="$OUT_DIR/phase_${phase}_tracer.log"
    local pidstat_log="$OUT_DIR/phase_${phase}_pidstat.log"
    local raw_out="$OUT_DIR/phase_${phase}_raw.log"
    local agg_out="$OUT_DIR/phase_${phase}_agg.log"

    echo ""
    echo "======================================================================"
    echo "  P1.3 Phase ${phase}  (with_tracer=${with_tracer})"
    echo "  Start: $(date)"
    echo "======================================================================"

    cleanup_procs
    echo "[${phase}] Waiting for HCCL cleanup (15s)..."
    sleep 15

    # Clean previous training output (full directory, recreated by training)
    rm -rf /root/mindformers/output 2>/dev/null || true

    local TRACE_PID=""
    # ---- Start eBPF tracer FIRST (Phase B only), verify before training ----
    if [ "$with_tracer" = "1" ]; then
        echo "[${phase}] Starting eBPF tracer..."
        /usr/bin/python3 -u "$TRACE_SCRIPT" \
            --min-size 1000 \
            --output "$raw_out" \
            --window-ms 100 \
            --agg-output "$agg_out" \
            > "$tracer_log" 2>&1 &
        TRACE_PID=$!
        echo "[${phase}] Tracer PID = $TRACE_PID"

        # Wait for BPF compilation + AscendCL library resolution
        echo "[${phase}] Waiting for BPF compilation (30s)..."
        sleep 30
        local LIB=""
        for i in $(seq 1 6); do
            if ! kill -0 "$TRACE_PID" 2>/dev/null; then
                echo "[${phase}] FATAL: tracer process died during startup"
                tail -20 "$tracer_log"
                cleanup_procs
                return 1
            fi
            LIB=$(grep "Using AscendCL" "$tracer_log" 2>/dev/null || echo "")
            if [ -n "$LIB" ]; then
                break
            fi
            sleep 5
        done
        if [ -z "$LIB" ]; then
            echo "[${phase}] FATAL: tracer did not mount AscendCL lib (60s)"
            tail -20 "$tracer_log"
            kill -9 "$TRACE_PID" 2>/dev/null || true
            cleanup_procs
            return 1
        fi
        echo "[${phase}] Tracer ready: $LIB"
    fi

    # ---- Start GLM-6B training ----
    echo "[${phase}] Starting GLM-6B training..."
    cd "$TRAIN_DIR"
    nohup bash -c "$TRAIN_CMD" > "$train_log" 2>&1 &
    sleep 5
    # Verify training launched (run_distribute spawns run_mindformer.py workers)
    if ! pgrep -f "[r]un_mindformer.py" >/dev/null 2>&1; then
        echo "[${phase}] WARN: run_mindformer.py not yet visible, waiting 10s more..."
        sleep 10
    fi
    echo "[${phase}] Training launched."
    local train_start_ts=$(date +%s)

    # ---- Warmup: wait until training reaches the data-producing phase ----
    if [ "$with_tracer" = "1" ]; then
        # Traced phase: wait until the eBPF tracer emits its first real record.
        echo "[${phase}] Waiting for first eBPF record (timeout ${WARMUP_TIMEOUT}s)..."
        local waited=0
        local rec=0
        while [ "$waited" -lt "$WARMUP_TIMEOUT" ]; do
            if ! kill -0 "$TRACE_PID" 2>/dev/null; then
                echo "[${phase}] FATAL: tracer died during warmup"
                tail -20 "$tracer_log"
                cleanup_procs
                return 1
            fi
            if ! pgrep -f "[r]un_mindformer.py" >/dev/null 2>&1; then
                echo "[${phase}] FATAL: training process gone during warmup"
                tail -20 "$train_log"
                cleanup_procs
                return 1
            fi
            rec=$(ebpf_record_count "$raw_out")
            if [ "$rec" -gt 0 ]; then
                break
            fi
            sleep 5
            waited=$(( waited + 5 ))
        done
        if [ "$rec" -le 0 ]; then
            echo "[${phase}] FATAL: no eBPF record within ${WARMUP_TIMEOUT}s"
            cleanup_procs
            return 1
        fi
        MEASURED_WARMUP=$(( $(date +%s) - train_start_ts ))
        echo "[${phase}] First eBPF record after ${MEASURED_WARMUP}s (${rec} records). Begin sampling."
    else
        # Baseline phase: reuse the warmup measured by the traced phase so both
        # phases sample at the same training maturity. Fallback to WARMUP_SEC.
        local warm="${MEASURED_WARMUP:-$WARMUP_SEC}"
        echo "[${phase}] Warmup ${warm}s (matched to traced phase)..."
        local waited=0
        while [ "$waited" -lt "$warm" ]; do
            if ! pgrep -f "[r]un_mindformer.py" >/dev/null 2>&1; then
                echo "[${phase}] FATAL: training process gone during warmup"
                tail -20 "$train_log"
                cleanup_procs
                return 1
            fi
            sleep 5
            waited=$(( waited + 5 ))
        done
        echo "[${phase}] Warmup done. Begin sampling."
    fi

    # Sample system CPU with mpstat
    local n_samples=$(( SAMPLE_SEC / SAMPLE_INTERVAL ))
    echo "[${phase}] Sampling ${SAMPLE_SEC}s (mpstat ${SAMPLE_INTERVAL}s x ${n_samples})..."
    mpstat "$SAMPLE_INTERVAL" "$n_samples" > "$mpstat_log" 2>&1 &
    local MPSTAT_PID=$!

    # Sample tracer process CPU with pidstat (only Phase B)
    if [ "$with_tracer" = "1" ] && [ -n "$TRACE_PID" ]; then
        pidstat -p "$TRACE_PID" "$SAMPLE_INTERVAL" "$n_samples" > "$pidstat_log" 2>&1 &
    fi

    wait "$MPSTAT_PID" 2>/dev/null || true
    echo "[${phase}] Sampling done at $(date)"

    # Stop tracer
    if [ -n "$TRACE_PID" ]; then
        kill -SIGINT "$TRACE_PID" 2>/dev/null || true
        sleep 2
        kill -9 "$TRACE_PID" 2>/dev/null || true
    fi

    # Stop training
    cleanup_procs
    sleep 3
    echo "[${phase}] Phase complete at $(date)"
}

echo "============================================================"
echo " P1.3 eBPF Overhead Measurement"
echo " Warmup=${WARMUP_SEC}s  Sample=${SAMPLE_SEC}s  Interval=${SAMPLE_INTERVAL}s"
echo " Started: $(date)"
echo "============================================================"

{
    echo "warmup_sec=$WARMUP_SEC"
    echo "sample_sec=$SAMPLE_SEC"
    echo "sample_interval=$SAMPLE_INTERVAL"
    echo "train_cmd=$TRAIN_CMD"
    echo "trace_script=$TRACE_SCRIPT"
    echo "start_time=$(date -Iseconds)"
    echo "ncpu=$(nproc)"
} > "$OUT_DIR/meta.txt"

# Phase B FIRST (with tracer): measures real time-to-first-eBPF-record warmup.
run_phase "b" "1" || { echo "Phase B failed"; cleanup_procs; exit 1; }

echo ""
echo "Cooldown 30s before Phase A..."
sleep 30

# Phase A (baseline, no tracer): reuses MEASURED_WARMUP from Phase B.
run_phase "a" "0" || { echo "Phase A failed"; cleanup_procs; exit 1; }

echo "measured_warmup_sec=$MEASURED_WARMUP" >> "$OUT_DIR/meta.txt"
echo "end_time=$(date -Iseconds)" >> "$OUT_DIR/meta.txt"

echo ""
echo "============================================================"
echo " P1.3 Collection DONE — $(date)"
echo " Output: $OUT_DIR"
ls -lh "$OUT_DIR"
echo "============================================================"
