#!/usr/bin/env python3
"""
带时间戳的 online_loop — 用于 P0.4 故障检测分析。

与原版 online_loop.py 的唯一区别：
  每次探针输出都带绝对时间戳 (ISO 8601 格式)

用法:
    cd /root/FlowGap-work/FlowGap-paper/code
    conda activate mindspore_py37
    PYTHONPATH=.:trace_parser python evaluation/online_loop_timestamped.py \
        --trace-log ../data/collected/p0.4_raw.log \
        --probe-policy flowgap_predictive \
        --predictor-model-path ../models/gbdt_pass1.pkl \
        --budget-per-sec 2 \
        | tee ../logs/p0.4_probe_ts.log
"""

from __future__ import annotations
import argparse, os, sys, time
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(CODE_DIR / "trace_parser"))

from trace_parser.parse_trace import parse_csv, group_by_path
from trace_parser.intervalize import build_timeline, Gap, BusyInterval
from trace_parser.schema import FlowEvent
from scheduler_replay.schema import ProbeType, ProbeConfig, ProbeOutcome, PROBE_LATENCY_SAME_NUMA_NS
from scheduler_replay.policies import make_policy, PolicyContext, GapSnapshot
from probe_scheduler.probe_executor import ProbeExecutor

PROBE_SIZES = {
    ProbeType.TINY_LATENCY: 4096,
    ProbeType.NORMAL_LATENCY: 4096,
    ProbeType.BANDWIDTH: 128 * 1024 * 1024,
}

PROBE_ITERATIONS = {
    ProbeType.TINY_LATENCY: 1,
    ProbeType.NORMAL_LATENCY: 10,
    ProbeType.BANDWIDTH: 1,
}


class OnlineProbeLoop:
    def __init__(self, trace_log_path: str, policy_name: str = "threshold",
                 budget_per_sec: int = 5, dry_run: bool = False,
                 once: bool = False, predictor_model_path: str = ""):
        self.trace_log_path = Path(trace_log_path)
        self.policy_name = policy_name
        self.budget_per_sec = budget_per_sec
        self.dry_run = dry_run
        self.once = once
        self._policy = make_policy(policy_name, predictor_model_path=predictor_model_path)
        self._ctx = PolicyContext()
        self._executor: Optional[ProbeExecutor] = None
        self._last_read_pos: int = 0
        self._running = False
        self._path_gaps: Dict[int, List[Gap]] = defaultdict(list)
        self._path_busy: Dict[int, List[BusyInterval]] = defaultdict(list)
        self._probing_window_sec = 1.0
        self._probes_this_window = 0
        self._window_start_time: float = 0.0
        self._total_probes = 0
        self._total_safe = 0
        self._total_unsafe = 0

    def start(self):
        print("=" * 60)
        print("FlowGap Online Probe Loop (Timestamped)")
        print(f"  Trace log:  {self.trace_log_path}")
        print(f"  Policy:     {self.policy_name}")
        print(f"  Budget:     {self.budget_per_sec} probes/s")
        print(f"  Dry run:    {self.dry_run}")
        print(f"  Once mode:  {self.once}")
        print("=" * 60)

        if not self.dry_run:
            print("\nOpening probe executor (AscendCL)...", flush=True)
            self._executor = ProbeExecutor(device_id=0)
            self._executor.open(max_probe_size=128 * 1024 * 1024)
            print("  OK — executor ready")

        self._running = True
        self._window_start_time = time.time()
        print(f"\nWaiting for trace file: {self.trace_log_path}")
        while not self.trace_log_path.exists():
            print(f"  Still waiting... ({time.strftime('%H:%M:%S')})")
            time.sleep(5)
        print("  Found. Starting to poll...")

        if self.once:
            self._process_full_file()
            return

        self._last_read_pos = self.trace_log_path.stat().st_size
        try:
            while self._running:
                self._poll_once()
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nInterrupted.")
        finally:
            self.stop()

    def _process_full_file(self):
        t0 = time.time()
        print("  Reading full file...", flush=True)
        all_events = parse_csv(str(self.trace_log_path))
        print(f"  Parsed {len(all_events)} events in {time.time()-t0:.1f}s", flush=True)
        by_path = group_by_path(all_events)
        path_gaps: Dict[int, List[Gap]] = {}
        total_gaps = 0
        for path_key, path_events in by_path.items():
            pid = hash(path_key) & 0xFFFF
            busy, gaps = build_timeline(path_events, 50_000, 100_000, pid)
            path_gaps[pid] = gaps
            total_gaps += len(gaps)
        print(f"  Built {len(by_path)} paths, {total_gaps} gaps in {time.time()-t0:.1f}s", flush=True)
        all_snaps: List[Tuple[int, Gap]] = []
        prev_durs: Dict[int, List[float]] = {}
        for pid, gaps in path_gaps.items():
            for g in gaps:
                all_snaps.append((pid, g))
        all_snaps.sort(key=lambda xs: xs[1].start_ns)
        for pid, gap in all_snaps:
            if pid not in prev_durs:
                prev_durs[pid] = []
            snap = GapSnapshot(path_id=pid, gap=gap, previous_gaps=list(prev_durs[pid]), previous_busy=[])
            self._handle_gap(pid, gap, snap)
            prev_durs[pid].append(float(gap.duration_ns))
            prev_durs[pid] = prev_durs[pid][-50:]
        print(f"  Processed {len(all_snaps)} gaps in {time.time()-t0:.1f}s", flush=True)
        print(f"\nTotal: {self._total_probes} probes, {self._total_safe} safe, {self._total_unsafe} unsafe")
        self._running = False

    def stop(self):
        self._running = False
        if self._executor:
            self._executor.close()
        print(f"\nFinal: {self._total_probes} probes, {self._total_safe} safe, {self._total_unsafe} unsafe")

    def _poll_once(self) -> bool:
        if not self.trace_log_path.exists():
            return False
        sz = self.trace_log_path.stat().st_size
        if sz <= self._last_read_pos:
            return False
        with open(self.trace_log_path, "r") as f:
            f.seek(self._last_read_pos)
            new_lines = f.readlines()
            self._last_read_pos = f.tell()
        if not new_lines:
            return False
        events = self._parse_lines(new_lines[1:])
        if not events:
            return False
        for path_key, path_events in group_by_path(events).items():
            path_id = hash(path_key) & 0xFFFF
            if not path_events:
                continue
            busy, gaps = build_timeline(path_events, 50_000, 100_000, path_id)
            if not gaps:
                continue
            self._path_busy[path_id] = busy
            old_gaps = self._path_gaps[path_id]
            new_gaps = [g for g in gaps if g not in old_gaps]
            self._path_gaps[path_id] = gaps
            for gap in new_gaps:
                self._handle_gap(path_id, gap)
        now = time.time()
        if now - self._window_start_time >= self._probing_window_sec:
            self._probes_this_window = 0
            self._window_start_time = now
        return True

    def _handle_gap(self, path_id: int, gap: Gap, snap: GapSnapshot = None):
        if snap is None:
            all_gaps = self._path_gaps.get(path_id, [])
            snap = GapSnapshot(
                path_id=path_id, gap=gap,
                previous_gaps=[float(g.duration_ns) for g in all_gaps[:-1]],
                previous_busy=list(self._path_busy.get(path_id, []))
            )
        if self._probes_this_window >= self.budget_per_sec:
            return
        decisions = self._policy(snap, self._ctx)
        if not decisions:
            return
        for probe_cfg in decisions:
            probe_time = PROBE_LATENCY_SAME_NUMA_NS.get(probe_cfg.probe_type, 50_000)
            if gap.duration_ns < probe_time:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                print(f"  [{ts}] [SKIP] Gap {gap.duration_ns/1e3:.0f}µs < probe {probe_time/1e3:.0f}µs", flush=True)
                continue
            self._probes_this_window += 1
            self._total_probes += 1
            if self.dry_run:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                print(f"  [{ts}] [DRY] Path {path_id}: {probe_cfg.probe_type.name} in gap {gap.duration_ns/1e3:.0f}µs", flush=True)
                self._total_safe += 1
                continue
            try:
                size = PROBE_SIZES.get(probe_cfg.probe_type, 4096)
                iters = PROBE_ITERATIONS.get(probe_cfg.probe_type, 1)
                if probe_cfg.probe_type == ProbeType.BANDWIDTH:
                    result = self._executor.probe_bandwidth("D2H")
                else:
                    result = self._executor.probe_latency(size, "D2H", iterations=iters)
                
                # 关键修改：输出带时间戳
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                if result.success:
                    self._total_safe += 1
                    label = "LAT" if probe_cfg.probe_type != ProbeType.BANDWIDTH else "BW"
                    print(f"  [{ts}] [{label}] Path {path_id}: {result.latency_us:.1f}µs ({result.bandwidth_gbps:.1f}GB/s)", flush=True)
                else:
                    self._total_unsafe += 1
                    print(f"  [{ts}] [FAIL] Path {path_id}: {result.error_msg}", flush=True)
            except Exception as e:
                self._total_unsafe += 1
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                print(f"  [{ts}] [ERR] Path {path_id}: {e}", flush=True)

    def _parse_lines(self, lines: List[str]) -> List[FlowEvent]:
        import tempfile
        csv_text = "PID,TID,Source,Destination,Size_MB,Latency_us,Bandwidth_GBps,Start_ns,End_ns,WallStart_ns,WallEnd_ns\n" + "".join(lines)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_text)
            tmp = f.name
        try:
            return parse_csv(tmp)
        finally:
            os.unlink(tmp)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-log", type=str, default="")
    parser.add_argument("--probe-policy", type=str, default="threshold",
                        choices=["no_probing", "fixed_interval", "random", "threshold", "ewma_only", "flowgap_predictive", "oracle"])
    parser.add_argument("--budget-per-sec", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--predictor-model-path", type=str, default="")
    args = parser.parse_args()
    loop = OnlineProbeLoop(
        trace_log_path=args.trace_log,
        policy_name=args.probe_policy,
        budget_per_sec=args.budget_per_sec,
        dry_run=args.dry_run,
        once=args.once,
        predictor_model_path=args.predictor_model_path,
    )
    loop.start()

if __name__ == "__main__":
    main()
