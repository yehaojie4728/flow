#!/usr/bin/python3
import argparse
import csv
import os
import re
from datetime import datetime


def normalize_fault(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def fault_family(text: str) -> str:
    if "NPU路径异常" in text:
        return "NPU"
    if "CPU链路异常" in text:
        return "CPU"
    if "内存通道异常" in text:
        return "NUMA"
    return "OTHER"


def parse_system_time_ns(line: str):
    if not line.startswith("[System Time]:"):
        return None
    raw = line.split(":", 1)[1].strip()
    try:
        return int(datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f").timestamp() * 1e9)
    except ValueError:
        return None


def parse_probe_log(path: str):
    loop_re = re.compile(r"\[Probe\] Triggered by Signal \(Loop (\d+)\)")
    fault_re = re.compile(r"^\s*-\s*\[(.+?)\]\s*(.+?)\s*$")
    summary_re = re.compile(r"\[汇总\]\s*实际探测到异常次数:\s*(\d+)")
    loops = {}
    current_loop = None
    in_fault_block = False
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            m_loop = loop_re.search(line)
            if m_loop:
                current_loop = int(m_loop.group(1))
                loops.setdefault(
                    current_loop,
                    {"faults": [], "reported_count": 0, "report_times_ns": [], "probe_start_wall_ns": None},
                )
                in_fault_block = False
                continue
            if current_loop is None:
                continue
            ts_ns = parse_system_time_ns(line)
            if ts_ns is not None:
                loops[current_loop]["report_times_ns"].append(ts_ns)
                if loops[current_loop]["probe_start_wall_ns"] is None:
                    loops[current_loop]["probe_start_wall_ns"] = ts_ns
                continue
            if "[故障分析]:" in line:
                in_fault_block = True
                continue
            if line.startswith("[Probe] Finished."):
                in_fault_block = False
                continue
            m_sum = summary_re.search(line)
            if m_sum:
                loops[current_loop]["reported_count"] += int(m_sum.group(1))
                in_fault_block = False
                continue
            if in_fault_block:
                m_fault = fault_re.match(line)
                if m_fault:
                    fault_text = f"[{m_fault.group(1)}] {m_fault.group(2)}"
                    loops[current_loop]["faults"].append(normalize_fault(fault_text))
    return loops


def parse_csv_rows(path: str):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        return list(reader)


def parse_agg_windows(path: str):
    windows = []
    for row in parse_csv_rows(path):
        try:
            windows.append(
                {
                    "window_start_ns": int(row["WindowStart_ns"]),
                    "window_end_ns": int(row["WindowEnd_ns"]),
                    "source": row["Source"],
                    "destination": row["Destination"],
                    "bytes_mb": float(row["Bytes_MB"]),
                    "bandwidth_gbps": float(row["Bandwidth_GBps"]),
                    "wall_start_ns": int(row.get("WindowStartWall_ns") or 0),
                    "wall_end_ns": int(row.get("WindowEndWall_ns") or 0),
                    "duration_ms": float(row.get("Duration_ms") or 0.0),
                    "packet_count": int(float(row.get("Packet_Count") or 0)),
                }
            )
        except (KeyError, ValueError):
            continue
    return windows


def overlap(start_a, end_a, start_b, end_b):
    return max(start_a, start_b) < min(end_a, end_b)


def find_window_covering_probe(probe_wall_ns, agg_windows):
    if probe_wall_ns is None:
        return None
    for item in agg_windows:
        if item["wall_start_ns"] and item["wall_end_ns"] and item["wall_start_ns"] <= probe_wall_ns <= item["wall_end_ns"]:
            return item
    for item in agg_windows:
        if item["wall_end_ns"] and item["wall_end_ns"] >= probe_wall_ns:
            return item
    return None


def classify_loops(loops, agg_windows, probe_bytes_mb, baseline_gbps, p2_ratio, p1_ratio):
    ordered = sorted(loops.keys())
    results = []
    for loop in ordered:
        info = loops[loop]
        times = sorted(info.get("report_times_ns", []))
        probe_start_wall_ns = info.get("probe_start_wall_ns") or (times[0] if times else None)
        probe_end_wall_ns = times[-1] if times else None
        faults = info["faults"]
        uniq_faults = []
        seen = set()
        for fault in faults:
            if fault not in seen:
                uniq_faults.append(fault)
                seen.add(fault)
        observed_window = find_window_covering_probe(probe_start_wall_ns, agg_windows)

        throughput_ratio = ""
        observed_bw = ""
        baseline_bw = f"{baseline_gbps:.2f}"
        trigger_source = ""
        trigger_destination = ""
        trigger_window_ns = ""
        merged_bw = ""
        severity = "P0"
        confidence = 85
        reasons = []

        if observed_window is not None:
            trigger_source = observed_window["source"]
            trigger_destination = observed_window["destination"]
            trigger_window_ns = f"{observed_window['window_start_ns']}-{observed_window['window_end_ns']}"
            observed_bw_value = observed_window["bandwidth_gbps"]
            observed_bw = f"{observed_bw_value:.2f}"
            duration_sec = max(1e-9, observed_window["duration_ms"] / 1000.0)
            merged_bw_value = (observed_window["bytes_mb"] + probe_bytes_mb) * 1024 * 1024 / duration_sec / 1e9
            merged_bw = f"{merged_bw_value:.2f}"
            ratio = merged_bw_value / baseline_gbps if baseline_gbps > 0 else 0.0
            throughput_ratio = f"{ratio:.3f}"
            reasons.append(
                f"probe时刻命中业务窗 {trigger_source} -> {trigger_destination}"
            )
            reasons.append(
                f"业务窗吞吐 {observed_bw_value:.2f} GB/s，加入probe流量后 {merged_bw_value:.2f} GB/s"
            )
            reasons.append(f"固定基线 {baseline_gbps * 8:.2f} Gbps (= {baseline_gbps:.2f} GB/s)")
            if ratio >= p2_ratio:
                severity = "P2"
                confidence = 30
                reasons.append(f"总吞吐达到基线 {ratio * 100:.1f}%")
            elif ratio >= p1_ratio:
                severity = "P1"
                confidence = 65
                reasons.append(f"总吞吐仅达到基线 {ratio * 100:.1f}%")
            else:
                severity = "P0"
                confidence = 90
                reasons.append(f"总吞吐仅达到基线 {ratio * 100:.1f}%")
        else:
            reasons.append("未找到probe时刻对应的业务时间窗，默认按 P0 输出")

        results.append(
            {
                "loop": loop,
                "severity": severity,
                "reason": " ; ".join(reasons),
                "confidence": confidence,
                "fault_count": len(uniq_faults),
                "reported_count": info["reported_count"] if info["reported_count"] else "",
                "trigger_source": trigger_source,
                "trigger_destination": trigger_destination,
                "matched_source": trigger_source,
                "matched_destination": trigger_destination,
                "trigger_window_ns": trigger_window_ns,
                "probe_start_wall_ns": probe_start_wall_ns if probe_start_wall_ns is not None else "",
                "probe_end_wall_ns": probe_end_wall_ns if probe_end_wall_ns is not None else "",
                "matched_window_start_ns": observed_window["window_start_ns"] if observed_window is not None else "",
                "matched_window_end_ns": observed_window["window_end_ns"] if observed_window is not None else "",
                "matched_window_start_wall_ns": observed_window["wall_start_ns"] if observed_window is not None else "",
                "matched_window_end_wall_ns": observed_window["wall_end_ns"] if observed_window is not None else "",
                "trigger_bandwidth_gbps": observed_bw,
                "probe_window_bandwidth_gbps": observed_bw,
                "baseline_bandwidth_gbps": baseline_bw,
                "baseline_bandwidth_gbps_bits": f"{baseline_gbps * 8:.2f}",
                "throughput_ratio": throughput_ratio,
                "probe_bytes_mb": f"{probe_bytes_mb:.2f}",
                "merged_bandwidth_gbps": merged_bw,
                "faults": " | ".join(uniq_faults),
            }
        )
    return results


def print_summary(results):
    print("Loop,Severity,TriggerSource,TriggerDestination,WindowBW,MergedBW,BaselineBW,Ratio,Reason")
    for item in results:
        print(
            f"{item['loop']},{item['severity']},{item['trigger_source']},{item['trigger_destination']},"
            f"{item['probe_window_bandwidth_gbps']},{item['merged_bandwidth_gbps']},{item['baseline_bandwidth_gbps']},"
            f"{item['throughput_ratio']},{item['reason']}"
        )


def write_csv(results, path):
    fieldnames = [
        "loop",
        "severity",
        "reason",
        "confidence",
        "fault_count",
        "reported_count",
        "trigger_source",
        "trigger_destination",
        "matched_source",
        "matched_destination",
        "trigger_window_ns",
        "probe_start_wall_ns",
        "probe_end_wall_ns",
        "matched_window_start_ns",
        "matched_window_end_ns",
        "matched_window_start_wall_ns",
        "matched_window_end_wall_ns",
        "trigger_bandwidth_gbps",
        "probe_window_bandwidth_gbps",
        "probe_bytes_mb",
        "merged_bandwidth_gbps",
        "baseline_bandwidth_gbps",
        "baseline_bandwidth_gbps_bits",
        "throughput_ratio",
        "faults",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            writer.writerow(item)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=os.path.join(root_dir, "logs/runtime/probe.log"))
    parser.add_argument("--agg-input", default=os.path.join(root_dir, "runs/agg/aclrtMemcpy_numa_trace.log"))
    parser.add_argument("--output", default=os.path.join(root_dir, "runs/severity/probe_severity.csv"))
    parser.add_argument("--probe-bytes-mb", type=float, default=256.0)
    parser.add_argument("--baseline-gbps", type=float, default=25.0)
    parser.add_argument("--p2-ratio", type=float, default=0.90)
    parser.add_argument("--p1-ratio", type=float, default=0.70)
    args = parser.parse_args()

    loops = parse_probe_log(args.input)
    agg_windows = parse_agg_windows(args.agg_input)
    results = classify_loops(
        loops,
        agg_windows,
        args.probe_bytes_mb,
        args.baseline_gbps,
        args.p2_ratio,
        args.p1_ratio,
    )
    print_summary(results)
    write_csv(results, args.output)
    print(f"\nwritten: {args.output}")


if __name__ == "__main__":
    main()
