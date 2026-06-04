#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/src/memcpy_benchmark.cpp"
OUT_DIR="$SCRIPT_DIR/build"
OUT_BIN="$OUT_DIR/memcpy_benchmark"

ASCEND_HOME="${ASCEND_TOOLKIT_HOME:-/usr/local/Ascend/ascend-toolkit/latest}"
INCLUDE_CANDIDATES=(
  "$ASCEND_HOME/include"
  "$ASCEND_HOME/aarch64-linux/include"
  "/usr/local/Ascend/cann-8.5.0/include"
  "/usr/local/Ascend/cann-8.5.0/aarch64-linux/include"
)
LIB_CANDIDATES=(
  "$ASCEND_HOME/lib64"
  "$ASCEND_HOME/aarch64-linux/lib64"
  "/usr/local/Ascend/cann-8.5.0/lib64"
  "/usr/local/Ascend/cann-8.5.0/aarch64-linux/lib64"
)

INCLUDE_DIR=""
LIB_DIR=""
NUMA_HEADER="/usr/include/numa.h"

for dir in "${INCLUDE_CANDIDATES[@]}"; do
  if [[ -d "$dir" ]]; then
    INCLUDE_DIR="$dir"
    break
  fi
done

for dir in "${LIB_CANDIDATES[@]}"; do
  if [[ -d "$dir" ]]; then
    LIB_DIR="$dir"
    break
  fi
done

if [[ -z "$INCLUDE_DIR" || -z "$LIB_DIR" ]]; then
  echo "[build.sh] 未找到 Ascend Toolkit 头文件或库目录，请设置 ASCEND_TOOLKIT_HOME。" >&2
  exit 1
fi

if [[ ! -f "$NUMA_HEADER" ]]; then
  echo "[build.sh] 缺少 NUMA 开发头文件: $NUMA_HEADER" >&2
  echo "[build.sh] Ubuntu/Debian 请先安装: apt-get update && apt-get install -y libnuma-dev" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

g++ -std=gnu++11 \
  -I"$INCLUDE_DIR" \
  "$SRC" \
  -o "$OUT_BIN" \
  -L"$LIB_DIR" \
  -Wl,-rpath,"$LIB_DIR" \
  -lascendcl -lpthread -lnuma

echo "[build.sh] built: $OUT_BIN"
