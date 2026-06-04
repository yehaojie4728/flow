# Probe Subproject

This directory contains the relocated `memcpy_benchmark` probe project.

## Layout

- `src/memcpy_benchmark.cpp`
  - resident single-link probe
  - waits for `SIGUSR1`
  - reads the target link from `PROBE_REQUEST_FILE`
  - runs `Bandwidth -> Latency`
  - no `8x8` matrix, no bidirectional round trip, no warmup
- `CMakeLists.txt`
  - standalone CMake entry
- `build.sh`
  - direct `g++` build helper for environments without `cmake`

## Runtime Contract

- `PROBE_STATUS_FILE`
  - output state file, values: `idle` / `busy`
- `PROBE_REQUEST_FILE`
  - one-line CSV request written by the adaptive daemon:

```text
request_id,trigger_wall_ns,source,destination,direction,device_id,numa_id,window_start_ns,window_end_ns,window_bw_gbps
```

## Build

Preferred:

```bash
cd /root/hostdiagv2/probe
cmake -S . -B build
cmake --build build -j
```

Fallback:

```bash
bash /root/hostdiagv2/probe/build.sh
```
