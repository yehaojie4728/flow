#!/usr/bin/python3
import argparse
import copy
import csv
import importlib.util
import json
import os
from datetime import datetime


DEFAULT_UPLOADER_SCRIPT = "/root/uploader/upload_topo.py"


def load_uploader_schema(script_path):
    spec = importlib.util.spec_from_file_location("upload_topo_runtime", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 uploader 脚本: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return list(csv.DictReader(f))


def parse_host_numa(text):
    prefix = "Host(NUMA "
    if not text.startswith(prefix) or not text.endswith(")"):
        return None
    try:
        return int(text[len(prefix):-1])
    except ValueError:
        return None


def parse_npu(text):
    prefix = "NPU "
    if not text.startswith(prefix):
        return None
    try:
        return int(text[len(prefix):])
    except ValueError:
        return None


def internal_cpu_by_numa(numa_id):
    if numa_id in (0, 1):
        return 0
    if numa_id in (2, 3):
        return 1
    if numa_id in (4, 5):
        return 2
    if numa_id in (6, 7):
        return 3
    return None


def internal_cpu_by_npu(npu_id):
    if npu_id in (4, 5):
        return 0
    if npu_id in (6, 7):
        return 1
    if npu_id in (2, 3):
        return 2
    if npu_id in (0, 1):
        return 3
    return None


def uploader_cpu_name(internal_cpu_id):
    if internal_cpu_id is None:
        return None
    return f"CPU{internal_cpu_id + 1}"


def uploader_npu_name(npu_id):
    if npu_id is None:
        return None
    return f"NPU{npu_id + 1}"


def normalize_link(a, b):
    return tuple(sorted((a, b)))


def map_row_to_uploader_link(row):
    src = row.get("matched_source") or row.get("trigger_source") or ""
    dst = row.get("matched_destination") or row.get("trigger_destination") or ""
    src_numa = parse_host_numa(src)
    dst_numa = parse_host_numa(dst)
    src_npu = parse_npu(src)
    dst_npu = parse_npu(dst)

    if src_numa is not None and dst_npu is not None:
        host_cpu = uploader_cpu_name(internal_cpu_by_numa(src_numa))
        npu_cpu = uploader_cpu_name(internal_cpu_by_npu(dst_npu))
        npu_name = uploader_npu_name(dst_npu)
        if host_cpu is None or npu_cpu is None or npu_name is None:
            return None
        if host_cpu == npu_cpu:
            return normalize_link(npu_name, host_cpu)
        return normalize_link(host_cpu, npu_cpu)

    if src_npu is not None and dst_numa is not None:
        npu_cpu = uploader_cpu_name(internal_cpu_by_npu(src_npu))
        host_cpu = uploader_cpu_name(internal_cpu_by_numa(dst_numa))
        npu_name = uploader_npu_name(src_npu)
        if host_cpu is None or npu_cpu is None or npu_name is None:
            return None
        if host_cpu == npu_cpu:
            return normalize_link(npu_name, host_cpu)
        return normalize_link(host_cpu, npu_cpu)

    if src_npu is not None and dst_npu is not None:
        return normalize_link(uploader_npu_name(src_npu), uploader_npu_name(dst_npu))

    return None


def choose_alarm_advice(severity):
    if severity == "P0":
        return "立即处置，检查链路健康度并切换热备设备。"
    if severity == "P1":
        return "尽快处置，排查链路带宽/时延异常并观察训练任务。"
    return "持续观察，优先检查任务负载、亲和性和调度策略。"


def ns_to_time_text(wall_ns):
    if not wall_ns:
        return ""
    dt = datetime.fromtimestamp(int(wall_ns) / 1e9)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def choose_better_alarm(current, candidate):
    severity_rank = {"P0": 3, "P1": 2, "P2": 1}
    current_rank = severity_rank.get(current.get("severity", ""), 0)
    candidate_rank = severity_rank.get(candidate.get("severity", ""), 0)
    if candidate_rank != current_rank:
        return candidate_rank > current_rank
    current_ratio = float(current.get("throughput_ratio") or 0.0)
    candidate_ratio = float(candidate.get("throughput_ratio") or 0.0)
    if candidate_ratio != current_ratio:
        return candidate_ratio < current_ratio
    return int(candidate.get("probe_start_wall_ns") or 0) > int(current.get("probe_start_wall_ns") or 0)


def build_alarm_desc(row):
    severity = row.get("severity", "")
    src = row.get("matched_source") or row.get("trigger_source") or ""
    dst = row.get("matched_destination") or row.get("trigger_destination") or ""
    merged_bw = row.get("merged_bandwidth_gbps") or ""
    baseline = row.get("baseline_bandwidth_gbps") or ""
    ratio = row.get("throughput_ratio") or ""
    try:
        ratio_pct = f"{float(ratio) * 100:.1f}%"
    except ValueError:
        ratio_pct = ratio
    return (
        f"{severity} 主机内链路异常: {src} -> {dst}; "
        f"总吞吐 {merged_bw} GB/s, 基线 {baseline} GB/s, 达标比例 {ratio_pct}"
    )


def build_payload(severity_rows, uploader_script_path):
    uploader = load_uploader_schema(uploader_script_path)
    base_links = []
    for item in uploader.LINKS:
        clean = dict(item)
        for key in (
            "alarm_desc",
            "alarm_time",
            "alarm_time_us",
            "alarm_adv",
            "severity",
            "reason",
            "probe_start_wall_ns",
            "probe_end_wall_ns",
            "matched_window_start_wall_ns",
            "matched_window_end_wall_ns",
            "throughput_ratio",
            "merged_bandwidth_gbps",
            "baseline_bandwidth_gbps",
        ):
            clean.pop(key, None)
        base_links.append(clean)
    payload = {
        "ip": uploader.get_interface_ip(),
        "hostname": uploader.get_hostname(),
        "nodes": copy.deepcopy(uploader.NODES),
        "links": base_links,
    }

    deduped = {}
    for row in severity_rows:
        link_key = map_row_to_uploader_link(row)
        if not link_key:
            continue
        existing = deduped.get(link_key)
        if existing is None or choose_better_alarm(existing, row):
            deduped[link_key] = row

    link_map = {}
    for item in payload["links"]:
        key = normalize_link(item["start"], item["end"])
        link_map[key] = item

    for link_key, row in deduped.items():
        start, end = link_key
        link_item = link_map.get(link_key)
        if link_item is None:
            link_item = {"start": start, "end": end}
            payload["links"].append(link_item)
            link_map[link_key] = link_item
        probe_start_wall_ns = int(row.get("probe_start_wall_ns") or 0)
        link_item["alarm_desc"] = build_alarm_desc(row)
        link_item["alarm_time"] = ns_to_time_text(probe_start_wall_ns)
        link_item["alarm_time_us"] = probe_start_wall_ns // 1000 if probe_start_wall_ns else 0
        link_item["alarm_adv"] = choose_alarm_advice(row.get("severity", ""))
        link_item["severity"] = row.get("severity", "")
        link_item["reason"] = row.get("reason", "")
        link_item["probe_start_wall_ns"] = probe_start_wall_ns
        link_item["probe_end_wall_ns"] = int(row.get("probe_end_wall_ns") or 0)
        link_item["matched_window_start_wall_ns"] = int(row.get("matched_window_start_wall_ns") or 0)
        link_item["matched_window_end_wall_ns"] = int(row.get("matched_window_end_wall_ns") or 0)
        link_item["throughput_ratio"] = float(row.get("throughput_ratio") or 0.0)
        link_item["merged_bandwidth_gbps"] = float(row.get("merged_bandwidth_gbps") or 0.0)
        link_item["baseline_bandwidth_gbps"] = float(row.get("baseline_bandwidth_gbps") or 0.0)

    return payload


def write_json(payload, output_path):
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    parser = argparse.ArgumentParser()
    parser.add_argument("--severity-input", default=os.path.join(root_dir, "runs/severity/probe_severity.csv"))
    parser.add_argument("--uploader-script", default=DEFAULT_UPLOADER_SCRIPT)
    parser.add_argument("--output", default=os.path.join(root_dir, "runs/severity/probe_topo_payload.json"))
    args = parser.parse_args()

    severity_rows = parse_csv_rows(args.severity_input)
    payload = build_payload(severity_rows, args.uploader_script)
    write_json(payload, args.output)
    print(f"written: {args.output}")


if __name__ == "__main__":
    main()
