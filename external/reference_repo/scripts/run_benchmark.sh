#!/bin/bash

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TRACE_SCRIPT="$ROOT_DIR/src/trace_memcpy_numa.py"
MINDFORMERS_DIR="/root/mindformers/scripts"
OUTPUT_DIR="/root/mindformers/output"
LOG_SRC_DIR="${OUTPUT_DIR}/log"
LOG_DEST_DIR="/root/log_with_trace"
RUN_CMD="bash run_distribute.sh /root/mindformers/mindformers/hccl_8p_01234567_192.168.39.155.json ../configs/glm/run_glm_6b_finetune.yaml '[0,8]' finetune"
WAIT_TIME="5h"

# Setup Environment
# Ensure we use the correct python for mindspore
source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37

echo "=================================================="
echo "Starting Benchmark Automation Script"
echo "Date: $(date)"
echo "=================================================="

# --- Phase 1: Training with Tracing ---
echo "[Phase 1] Starting Training WITH Tracing..."

# 1. Start Trace in background
echo "-> Starting trace_memcpy_numa.py in background..."
cd "$ROOT_DIR"
# Use nohup to ignore HUP signal (SSH disconnect)
nohup /usr/bin/python3 "$TRACE_SCRIPT" --min-size 1000 > trace_output.log 2>&1 &
TRACE_PID=$!
echo "-> Trace started with PID: $TRACE_PID"

# 2. Start Training
echo "-> Starting training task..."
cd $MINDFORMERS_DIR
# Using bash -c to properly handle quotes in arguments with nohup
nohup bash -c "$RUN_CMD" > training_phase1.log 2>&1 &
TRAIN_PID=$!
echo "-> Training started with PID: $TRAIN_PID"

# 3. Wait for training to complete
echo "-> Waiting for $WAIT_TIME..."
sleep $WAIT_TIME

# 4. Stop Trace
echo "-> Time is up. Stopping trace..."
kill -SIGTERM $TRACE_PID
wait $TRACE_PID 2>/dev/null
echo "-> Trace stopped."

# 5. Stop Training (Ensure it's stopped before cleanup)
echo "-> Stopping training processes..."
pkill -P $TRAIN_PID
kill $TRAIN_PID 2>/dev/null
# Force kill any remaining python processes related to training just in case
pkill -f "run_mindformer.py"
echo "-> Training processes stopped."

# 6. Backup Logs
echo "-> Backing up logs to $LOG_DEST_DIR..."
# Ensure destination parent exists
mkdir -p $(dirname $LOG_DEST_DIR)
# Copy log directory
if [ -d "$LOG_SRC_DIR" ]; then
    cp -r $LOG_SRC_DIR $LOG_DEST_DIR
    echo "-> Logs backed up successfully."
else
    echo "-> WARNING: Log directory $LOG_SRC_DIR does not exist!"
fi

# 7. Clear Output
echo "-> Clearing output directory ($OUTPUT_DIR)..."
rm -rf $OUTPUT_DIR/*
echo "-> Output directory cleared."

# --- Phase 2: Training without Tracing ---
echo "[Phase 2] Starting Training WITHOUT Tracing..."

# 8. Re-run Training
echo "-> Starting training task (Phase 2)..."
cd $MINDFORMERS_DIR
nohup bash -c "$RUN_CMD" > training_phase2.log 2>&1 &
TRAIN_PID_2=$!
echo "-> Training (Phase 2) started with PID: $TRAIN_PID_2"

echo "=================================================="
echo "Benchmark Script Completed."
echo "Phase 2 training is running in background (PID: $TRAIN_PID_2)."
echo "You can disconnect now."
echo "=================================================="
