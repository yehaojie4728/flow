#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs/runtime"
PROBE_PID_FILE="$LOG_DIR/probe.pid"
PROBE_STATUS_FILE="${PROBE_STATUS_FILE:-$LOG_DIR/probe.status}"
PROBE_REQUEST_FILE="${PROBE_REQUEST_FILE:-$LOG_DIR/probe_request.csv}"
DAEMON_PID_FILE="$LOG_DIR/daemon.pid"
EBPF_PID_FILE="$LOG_DIR/ebpf.pid"
ANALYZER_PID_FILE="$LOG_DIR/analyzer.pid"
RUN_DIR="$ROOT_DIR/runs"
PROBE_SEVERITY_CSV="${PROBE_SEVERITY_CSV:-$RUN_DIR/severity/probe_severity.csv}"
PROBE_TOPO_PAYLOAD="${PROBE_TOPO_PAYLOAD:-$RUN_DIR/severity/probe_topo_payload.json}"

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

kill_by_pid_file() {
  local f="$1"
  if [[ -f "$f" ]]; then
    local pid
    pid="$(cat "$f" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      sleep 1
      if kill -0 "$pid" >/dev/null 2>&1; then
        kill -9 "$pid" >/dev/null 2>&1 || true
      fi
    fi
  fi
}

kill_by_pid_file "$DAEMON_PID_FILE"
kill_by_pid_file "$EBPF_PID_FILE"
kill_by_pid_file "$PROBE_PID_FILE"
kill_by_pid_file "$ANALYZER_PID_FILE"

pkill -f npu_adaptive_daemon >/dev/null 2>&1 || true
pkill -f trace_memcpy_numa.py >/dev/null 2>&1 || true
pkill -f probe_analysis_worker.py >/dev/null 2>&1 || true
if PROBE_BIN_RESOLVED="$(resolve_probe_bin 2>/dev/null)"; then
  pkill -f "^${PROBE_BIN_RESOLVED}$" >/dev/null 2>&1 || true
else
  pkill -f 'memcpy_benchmark' >/dev/null 2>&1 || true
fi

rm -f "$DAEMON_PID_FILE" "$EBPF_PID_FILE" "$PROBE_PID_FILE" "$ANALYZER_PID_FILE" "$PROBE_STATUS_FILE" "$PROBE_REQUEST_FILE"

echo "停止完成"
echo "保留结果文件:"
ls -l "$PROBE_SEVERITY_CSV" "$PROBE_TOPO_PAYLOAD" 2>/dev/null || true
pgrep -af 'memcpy_benchmark|trace_memcpy_numa.py|npu_adaptive_daemon|probe_analysis_worker.py' || true
