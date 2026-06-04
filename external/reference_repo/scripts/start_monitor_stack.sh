#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs/runtime"
RUN_DIR="$ROOT_DIR/runs"
RAW_TRACE_LOG="${RAW_TRACE_LOG:-$RUN_DIR/raw/aclrtMemcpy_numa_raw.log}"
AGG_OUTPUT="${AGG_OUTPUT:-$RUN_DIR/agg/aclrtMemcpy_numa_trace.log}"
TRIGGER_LOG="${TRIGGER_LOG:-$RUN_DIR/agg/probe_trigger_windows.csv}"
DAEMON_SRC="$ROOT_DIR/src/npu_adaptive_daemon.cpp"
DAEMON_BIN="$ROOT_DIR/bin/npu_adaptive_daemon"
PROBE_PID_FILE="$LOG_DIR/probe.pid"
PROBE_STATUS_FILE="${PROBE_STATUS_FILE:-$LOG_DIR/probe.status}"
PROBE_REQUEST_FILE="${PROBE_REQUEST_FILE:-$LOG_DIR/probe_request.csv}"
DAEMON_PID_FILE="$LOG_DIR/daemon.pid"
EBPF_PID_FILE="$LOG_DIR/ebpf.pid"
ANALYZER_PID_FILE="$LOG_DIR/analyzer.pid"
E_BPF_PY="${E_BPF_PY:-$ROOT_DIR/src/trace_memcpy_numa.py}"
ANALYZER_PY="${ANALYZER_PY:-$ROOT_DIR/src/probe_severity_analyzer.py}"
ANALYSIS_WORKER_PY="${ANALYSIS_WORKER_PY:-$ROOT_DIR/src/probe_analysis_worker.py}"
EXPORT_UPLOADER_PY="${EXPORT_UPLOADER_PY:-$ROOT_DIR/src/export_uploader_topo.py}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
MIN_SIZE="${MIN_SIZE:-1048576}"
WINDOW_MS="${WINDOW_MS:-100}"
LOW_MBPS="${LOW_MBPS:-800}"
HIGH_MBPS="${HIGH_MBPS:-26000}"
COOLDOWN_SEC="${COOLDOWN_SEC:-3}"
PROBE_REQUIRED="${PROBE_REQUIRED:-0}"
PROBE_SEVERITY_CSV="${PROBE_SEVERITY_CSV:-$RUN_DIR/severity/probe_severity.csv}"
PROBE_TOPO_PAYLOAD="${PROBE_TOPO_PAYLOAD:-$RUN_DIR/severity/probe_topo_payload.json}"
UPLOADER_SCRIPT="${UPLOADER_SCRIPT:-/root/uploader/upload_topo.py}"

resolve_probe_bin() {
  local candidates=()
  if [[ -n "${PROBE_BIN:-}" ]]; then
    candidates+=("$PROBE_BIN")
  else
    candidates+=("$ROOT_DIR/probe/build/memcpy_benchmark")
  fi
  candidates+=(
    "$ROOT_DIR/probe/build/memcpy_benchmark"
    "$ROOT_DIR/probe/bin/memcpy_benchmark"
    "/root/npu_diagv3/build/memcpy_benchmark"
    "/root/npu_diagv3/memcpy_benchmark"
    "$ROOT_DIR/bin/memcpy_benchmark"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" && -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

PROBE_BIN_RESOLVED=""
if PROBE_BIN_RESOLVED="$(resolve_probe_bin)"; then
  PROBE_BIN="$PROBE_BIN_RESOLVED"
else
  PROBE_BIN=""
fi

mkdir -p "$LOG_DIR" "$RUN_DIR/raw" "$RUN_DIR/agg" "$RUN_DIR/severity" "$ROOT_DIR/bin"

require_file() {
  local path="$1"
  local desc="$2"
  if [[ ! -f "$path" ]]; then
    echo "[start_monitor_stack] 缺少${desc}: $path" >&2
    exit 1
  fi
}

require_file "$DAEMON_SRC" "daemon源码"
require_file "$E_BPF_PY" "eBPF脚本"
require_file "$ANALYZER_PY" "probe分级脚本"
require_file "$ANALYSIS_WORKER_PY" "probe实时分析脚本"
require_file "$EXPORT_UPLOADER_PY" "uploader导出脚本"
if [[ -n "$PROBE_BIN" ]]; then
  require_file "$PROBE_BIN" "probe可执行文件"
  chmod +x "$PROBE_BIN" >/dev/null 2>&1 || true
fi

pkill -f npu_adaptive_daemon >/dev/null 2>&1 || true
pkill -f trace_memcpy_numa.py >/dev/null 2>&1 || true
pkill -f probe_analysis_worker.py >/dev/null 2>&1 || true
if [[ -n "$PROBE_BIN" ]]; then
  pkill -f "^${PROBE_BIN}$" >/dev/null 2>&1 || true
else
  pkill -f 'memcpy_benchmark' >/dev/null 2>&1 || true
fi
sleep 1

g++ -O2 "$DAEMON_SRC" -o "$DAEMON_BIN"

rm -f "$PROBE_PID_FILE" "$EBPF_PID_FILE" "$DAEMON_PID_FILE" "$ANALYZER_PID_FILE"
rm -f "$PROBE_STATUS_FILE" "$PROBE_REQUEST_FILE"
: > "$LOG_DIR/probe.log"
: > "$LOG_DIR/ebpf.log"
: > "$LOG_DIR/daemon.log"
: > "$LOG_DIR/analyzer.log"
: > "$RAW_TRACE_LOG"
: > "$AGG_OUTPUT"
: > "$TRIGGER_LOG"
rm -f "$PROBE_SEVERITY_CSV" "$PROBE_TOPO_PAYLOAD"

if [[ -n "$PROBE_BIN" ]]; then
  PROBE_STATUS_FILE="$PROBE_STATUS_FILE" PROBE_REQUEST_FILE="$PROBE_REQUEST_FILE" \
    nohup stdbuf -oL -eL "$PROBE_BIN" > "$LOG_DIR/probe.log" 2>&1 &
  echo $! > "$PROBE_PID_FILE"

  for _ in $(seq 1 20); do
    PROBE_PID="$(cat "$PROBE_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${PROBE_PID}" ]] && kill -0 "$PROBE_PID" >/dev/null 2>&1; then
      if grep -q 'Monitor Started' "$LOG_DIR/probe.log" 2>/dev/null; then
        break
      fi
    fi
    sleep 0.2
  done
else
  rm -f "$PROBE_PID_FILE"
  if [[ "$PROBE_REQUIRED" == "1" ]]; then
    echo "[start_monitor_stack] 未找到 probe 可执行文件，请通过 PROBE_BIN 指定。" >&2
    exit 1
  fi
  echo "[start_monitor_stack] Warning: 未找到 probe，可先运行 eBPF 监控；若需要联动探测，请设置 PROBE_BIN。" | tee -a "$LOG_DIR/probe.log"
fi

nohup "$PYTHON_BIN" -u "$E_BPF_PY" \
  --min-size "$MIN_SIZE" \
  --output "$RAW_TRACE_LOG" \
  --window-ms "$WINDOW_MS" \
  --agg-output "$AGG_OUTPUT" \
  > "$LOG_DIR/ebpf.log" 2>&1 &
echo $! > "$EBPF_PID_FILE"

EBPF_PID="$(cat "$EBPF_PID_FILE" 2>/dev/null || true)"
for _ in $(seq 1 10); do
  if [[ -z "$EBPF_PID" ]] || ! kill -0 "$EBPF_PID" >/dev/null 2>&1; then
    echo "[start_monitor_stack] eBPF 进程启动失败，请检查 $LOG_DIR/ebpf.log" >&2
    tail -n 20 "$LOG_DIR/ebpf.log" >&2 || true
    exit 1
  fi
  if grep -q 'Monitoring started' "$LOG_DIR/ebpf.log" 2>/dev/null; then
    break
  fi
  if grep -Eq 'Traceback|Exception: Failed to compile BPF module|Operation not permitted' "$LOG_DIR/ebpf.log" 2>/dev/null; then
    echo "[start_monitor_stack] eBPF 初始化失败，请检查 $LOG_DIR/ebpf.log" >&2
    tail -n 20 "$LOG_DIR/ebpf.log" >&2 || true
    exit 1
  fi
  sleep 0.5
done

if [[ -n "$PROBE_BIN" ]]; then
  nohup stdbuf -oL -eL "$DAEMON_BIN" \
    --log-file "$AGG_OUTPUT" \
    --benchmark-cmd "$PROBE_BIN" \
    --probe-pid-file "$PROBE_PID_FILE" \
    --probe-status-file "$PROBE_STATUS_FILE" \
    --probe-request-file "$PROBE_REQUEST_FILE" \
    --trigger-log-file "$TRIGGER_LOG" \
    --low "$LOW_MBPS" \
    --high "$HIGH_MBPS" \
    --cooldown "$COOLDOWN_SEC" \
    > "$LOG_DIR/daemon.log" 2>&1 &
  echo $! > "$DAEMON_PID_FILE"
else
  rm -f "$DAEMON_PID_FILE"
  echo "[start_monitor_stack] Probe 未启动，跳过 daemon 联动。" | tee -a "$LOG_DIR/daemon.log"
fi

nohup "$PYTHON_BIN" -u "$ANALYSIS_WORKER_PY" \
  --input "$LOG_DIR/probe.log" \
  --agg-input "$AGG_OUTPUT" \
  --output "$PROBE_SEVERITY_CSV" \
  --topo-output "$PROBE_TOPO_PAYLOAD" \
  --uploader-script "$UPLOADER_SCRIPT" \
  > "$LOG_DIR/analyzer.log" 2>&1 &
echo $! > "$ANALYZER_PID_FILE"

echo "启动完成"
if [[ -f "$PROBE_PID_FILE" ]]; then
  echo "probe.pid=$(cat "$PROBE_PID_FILE")"
else
  echo "probe.pid=disabled"
fi
echo "ebpf.pid=$(cat "$EBPF_PID_FILE")"
if [[ -f "$DAEMON_PID_FILE" ]]; then
  echo "daemon.pid=$(cat "$DAEMON_PID_FILE")"
else
  echo "daemon.pid=disabled"
fi
echo "analyzer.pid=$(cat "$ANALYZER_PID_FILE")"
echo "root_dir=$ROOT_DIR"
echo "probe_bin=${PROBE_BIN:-disabled}"
echo "probe_status_file=$PROBE_STATUS_FILE"
echo "probe_request_file=$PROBE_REQUEST_FILE"
echo "probe_severity_csv=$PROBE_SEVERITY_CSV"
echo "probe_topo_payload=$PROBE_TOPO_PAYLOAD"
echo "window_ms=$WINDOW_MS all_links=true"
echo "raw_trace_log=$RAW_TRACE_LOG"
echo "agg_output(monitor_input)=$AGG_OUTPUT"
echo "trigger_log=$TRIGGER_LOG"
echo "进程检查:"
pgrep -af 'memcpy_benchmark|trace_memcpy_numa.py|npu_adaptive_daemon|probe_analysis_worker.py' || true
echo "日志文件:"
ls -l --time-style=long-iso "$LOG_DIR/probe.log" "$LOG_DIR/ebpf.log" "$LOG_DIR/daemon.log" "$LOG_DIR/analyzer.log"
