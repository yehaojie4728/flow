#!/usr/bin/env python3
"""
P1.3 eBPF Tracer Overhead Analysis

Parses mpstat/pidstat logs produced by collect_p1.3_ebpf_overhead.sh and
computes the CPU overhead introduced by the eBPF tracer.

Two complementary metrics:
  1. System CPU delta : (busy% with tracer) - (busy% baseline)
  2. Tracer process CPU: tracer's own %CPU (from pidstat), normalized by ncpu

Output: code/results/P1.3_ebpf_overhead/
  - overhead_analysis.json
  - overhead_report.md
"""
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
DATA_DIR = ROOT / "data" / "collected" / "p1.3_overhead"
RESULTS_DIR = ROOT / "code" / "results" / "P1.3_ebpf_overhead"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def parse_meta(path: Path) -> dict:
    meta = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                meta[k.strip()] = v.strip()
    return meta


def parse_mpstat_idle(path: Path):
    """Extract %idle values from 'all' rows of an mpstat log.

    Returns list of busy% (100 - idle) per sample.
    """
    if not path.exists():
        return []
    busy = []
    header_cols = None
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts:
            continue
        # Locate header to find %idle column index
        if "%idle" in parts:
            header_cols = parts
            continue
        # Data rows: second token is "all"
        if header_cols and len(parts) >= len(header_cols):
            # mpstat rows start with a time token; align by matching 'all'
            if "all" in parts:
                try:
                    idle_idx_in_header = header_cols.index("%idle")
                    # header has no leading time token offset vs data: both include CPU col.
                    # Data row layout: TIME all <metrics...>; header: TIME(or AM/PM) CPU <metrics>
                    # Use offset from the 'all'/'CPU' anchor instead.
                    all_pos = parts.index("all")
                    cpu_pos = header_cols.index("CPU") if "CPU" in header_cols else 1
                    idle_val = float(parts[all_pos + (idle_idx_in_header - cpu_pos)])
                    busy.append(100.0 - idle_val)
                except (ValueError, IndexError):
                    continue
    return busy


def parse_pidstat_cpu(path: Path):
    """Extract %CPU values for the tracer process from a pidstat log."""
    if not path.exists():
        return []
    cpus = []
    header_cols = None
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts:
            continue
        if "%CPU" in parts:
            header_cols = parts
            continue
        if header_cols and "%CPU" in header_cols:
            # Skip the trailing "Average" summary line to avoid double counting
            if parts[0].lower() == "average:":
                continue
            try:
                cpu_idx = header_cols.index("%CPU")
                # pidstat data rows have a leading time token not present in some headers;
                # align by counting from the end is unreliable, so match by Command at end.
                # Standard layout: TIME UID PID %usr %system %guest %wait %CPU CPU Command
                # Find %CPU by locating the numeric before the CPU-core integer + command.
                val = float(parts[cpu_idx])
                cpus.append(val)
            except (ValueError, IndexError):
                # Fallback: try known fixed position (7th metric)
                continue
    return cpus


def summarize(vals):
    if not vals:
        return None
    return {
        "n": len(vals),
        "mean": round(statistics.mean(vals), 4),
        "median": round(statistics.median(vals), 4),
        "stdev": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
    }


def main():
    print("=" * 60)
    print("P1.3 eBPF Tracer Overhead Analysis")
    print("=" * 60)

    meta = parse_meta(DATA_DIR / "meta.txt")
    ncpu = int(meta.get("ncpu", "0")) or None

    a_busy = parse_mpstat_idle(DATA_DIR / "phase_a_mpstat.log")
    b_busy = parse_mpstat_idle(DATA_DIR / "phase_b_mpstat.log")
    tracer_cpu = parse_pidstat_cpu(DATA_DIR / "phase_b_pidstat.log")

    if not a_busy or not b_busy:
        print(f"ERROR: missing mpstat samples (A={len(a_busy)}, B={len(b_busy)})")
        print(f"  Looked in: {DATA_DIR}")
        sys.exit(1)

    a_sum = summarize(a_busy)
    b_sum = summarize(b_busy)
    tracer_sum = summarize(tracer_cpu)

    # System-level overhead: busy% delta
    sys_overhead_pp = round(b_sum["mean"] - a_sum["mean"], 4)  # percentage points

    # Tracer process overhead normalized to whole machine
    tracer_overhead_pct = None
    if tracer_sum and ncpu:
        # pidstat %CPU is relative to a single core; divide by ncpu for system fraction
        tracer_overhead_pct = round(tracer_sum["mean"] / ncpu, 4)

    result = {
        "config": meta,
        "ncpu": ncpu,
        "phase_a_baseline_busy_pct": a_sum,
        "phase_b_traced_busy_pct": b_sum,
        "tracer_process_cpu_pct_per_core": tracer_sum,
        "overhead": {
            "system_busy_delta_pp": sys_overhead_pp,
            "tracer_process_system_pct": tracer_overhead_pct,
        },
    }

    json_path = RESULTS_DIR / "overhead_analysis.json"
    json_path.write_text(json.dumps(result, indent=2))
    print(f"\nSaved: {json_path}")

    # Report
    lines = [
        "# P1.3 eBPF Tracer Overhead Analysis",
        "",
        f"**Method**: GLM-6B training, mpstat system sampling + pidstat tracer sampling",
        f"**Config**: warmup={meta.get('warmup_sec','?')}s, sample={meta.get('sample_sec','?')}s, "
        f"interval={meta.get('sample_interval','?')}s, ncpu={ncpu}",
        "",
        "## System CPU Utilization (busy% = 100 - idle)",
        "",
        "| Phase | Samples | Mean busy% | Median | Stdev | Min | Max |",
        "|-------|---------|-----------|--------|-------|-----|-----|",
        f"| A (baseline, no tracer) | {a_sum['n']} | {a_sum['mean']} | {a_sum['median']} | {a_sum['stdev']} | {a_sum['min']} | {a_sum['max']} |",
        f"| B (with eBPF tracer)    | {b_sum['n']} | {b_sum['mean']} | {b_sum['median']} | {b_sum['stdev']} | {b_sum['min']} | {b_sum['max']} |",
        "",
        f"**System CPU overhead**: {sys_overhead_pp:+.4f} percentage points "
        f"({b_sum['mean']}% - {a_sum['mean']}%)",
        "",
    ]
    if tracer_sum:
        lines += [
            "## Tracer Process CPU (pidstat, %CPU relative to single core)",
            "",
            "| Samples | Mean | Median | Stdev | Min | Max |",
            "|---------|------|--------|-------|-----|-----|",
            f"| {tracer_sum['n']} | {tracer_sum['mean']} | {tracer_sum['median']} | {tracer_sum['stdev']} | {tracer_sum['min']} | {tracer_sum['max']} |",
            "",
        ]
        if tracer_overhead_pct is not None:
            lines.append(
                f"**Tracer process whole-system CPU**: {tracer_overhead_pct}% "
                f"(= {tracer_sum['mean']}% / {ncpu} cores)"
            )
            lines.append("")

    lines += [
        "## Interpretation",
        "",
        f"- The eBPF tracer adds **{sys_overhead_pp:+.4f} pp** to system CPU busy ratio during training.",
    ]
    if tracer_overhead_pct is not None:
        lines.append(
            f"- The tracer user-space process itself consumes **{tracer_overhead_pct}%** of total machine CPU."
        )
    lines.append("")

    md_path = RESULTS_DIR / "overhead_report.md"
    md_path.write_text("\n".join(lines))
    print(f"Report: {md_path}")

    print("\n--- Summary ---")
    print(f"Baseline busy%: {a_sum['mean']}")
    print(f"Traced   busy%: {b_sum['mean']}")
    print(f"System overhead: {sys_overhead_pp:+.4f} pp")
    if tracer_overhead_pct is not None:
        print(f"Tracer process: {tracer_overhead_pct}% of machine")
    print("Done.")


if __name__ == "__main__":
    main()
