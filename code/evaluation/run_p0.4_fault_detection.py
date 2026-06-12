#!/usr/bin/env python3
"""
P0.4: 故障注入检测分析

从带时间戳的探针日志中检测带宽下降事件,计算:
  - 检测延迟 (故障注入 → 首次检测到带宽下降的时间)
  - 召回率 (故障期间被探针标记为异常的比例)
  - 带宽 time series

输入:
  --probe-log    带时间戳的探针日志 (probe_live_p0.4.log)
  --fault-start  故障注入开始时间 (Unix 秒, 或相对训练起始的秒数)
  --fault-end    故障注入结束时间
  --baseline-gbps 正常带宽基线 (从故障前的探针估算, 默认自动计算)
  --threshold    带宽下降判定阈值 (默认 0.7 = 下降到基线 70% 以下算异常)

输出: results/p0.4_fault_detection/
  - fault_detection.json
  - fault_detection_report.txt
  - bandwidth_timeseries.csv
"""
import argparse
import json
import re
import sys
from pathlib import Path
from statistics import mean, median

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
RESULTS_DIR = ROOT / "code" / "results" / "p0.4_fault_detection"


# 带时间戳的探针日志格式 (online_loop.py 需输出时间戳):
#   [2026-06-11 15:30:42.123] [BW] Path 39006: 6580.7µs (20.4GB/s)
# 兼容无时间戳的旧格式:
#   [BW] Path 39006: 6580.7µs (20.4GB/s)
TS_PATTERN = re.compile(
    r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]\s*'
    r'\[(\w+)\] Path (\d+): ([\d.]+)µs \(([\d.]+)GB/s\)'
)
NO_TS_PATTERN = re.compile(r'\[(\w+)\] Path (\d+): ([\d.]+)µs \(([\d.]+)GB/s\)')


def parse_timestamp(ts_str):
    """解析时间戳字符串为 Unix 秒 (float)。"""
    from datetime import datetime
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in ts_str else "%Y-%m-%d %H:%M:%S"
    return datetime.strptime(ts_str, fmt).timestamp()


def parse_probe_log(log_path):
    """解析探针日志,返回带时间戳的探针列表。

    返回: [{"t": float秒, "type": str, "path_id": int,
            "latency_us": float, "bandwidth_gbps": float}, ...]
    如果日志无时间戳,t 字段为 None (无法计算检测延迟,仅能算召回率)。
    """
    probes = []
    has_ts = False
    with open(log_path) as f:
        for line in f:
            m = TS_PATTERN.search(line)
            if m:
                has_ts = True
                probes.append({
                    "t": parse_timestamp(m.group(1)),
                    "type": m.group(2),
                    "path_id": int(m.group(3)),
                    "latency_us": float(m.group(4)),
                    "bandwidth_gbps": float(m.group(5)),
                })
                continue
            m = NO_TS_PATTERN.search(line)
            if m:
                probes.append({
                    "t": None,
                    "type": m.group(1),
                    "path_id": int(m.group(2)),
                    "latency_us": float(m.group(3)),
                    "bandwidth_gbps": float(m.group(4)),
                })
    return probes, has_ts


def main():
    ap = argparse.ArgumentParser(description="P0.4 故障注入检测分析")
    ap.add_argument("--probe-log", required=True, help="带时间戳的探针日志路径")
    ap.add_argument("--fault-start", type=float, default=None,
                    help="故障注入开始时间 (Unix 秒)")
    ap.add_argument("--fault-end", type=float, default=None,
                    help="故障注入结束时间 (Unix 秒)")
    ap.add_argument("--baseline-end", type=float, default=None,
                    help="基线计算截止时间 (Unix 秒)。默认: fault-start")
    ap.add_argument("--baseline-gbps", type=float, default=None,
                    help="正常带宽基线 GB/s (默认: 基线期 BW 探针中位数)")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="带宽下降判定阈值 (默认 0.7)")
    ap.add_argument("--detect-window", type=int, default=2,
                    help="连续 N 次低带宽才确认检测 (抗抖动, 默认 2)")
    args = ap.parse_args()

    log_path = Path(args.probe_log)
    if not log_path.exists():
        print(f"ERROR: 探针日志不存在: {log_path}")
        sys.exit(1)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("P0.4: 故障注入检测分析")
    print("=" * 60)

    probes, has_ts = parse_probe_log(log_path)
    bw_probes = [p for p in probes if p["type"] == "BW"]
    print(f"\n解析到 {len(probes)} 次探针 ({len(bw_probes)} 次带宽探针)")

    if len(bw_probes) == 0:
        print("ERROR: 没有带宽探针记录,无法做故障检测分析")
        sys.exit(1)

    if not has_ts:
        print("\n⚠ 警告: 日志无时间戳。无法计算检测延迟。")
        print("  请使用 online_loop.py 的 --timestamp 选项重新采集真机日志。")

    analyze(bw_probes, has_ts, args)


def analyze(bw_probes, has_ts, args):
    """核心分析逻辑。"""
    fault_start = args.fault_start
    fault_end = args.fault_end
    baseline_end = args.baseline_end or fault_start  # 默认用 fault_start
    baseline_gbps = args.baseline_gbps
    threshold = args.threshold
    detect_window = args.detect_window

    # 1. 计算基线带宽 (如果未指定)
    if baseline_gbps is None:
        if has_ts and baseline_end is not None:
            # 用 baseline_end 之前的探针计算干净基线
            before_fault = [p["bandwidth_gbps"] for p in bw_probes if p["t"] < baseline_end]
        else:
            # 无时间戳或未指定: 用前 1/3 探针作为基线
            n = len(bw_probes) // 3
            before_fault = [p["bandwidth_gbps"] for p in bw_probes[:n]]
        
        if len(before_fault) == 0:
            print("ERROR: 无法计算基线带宽 (基线期无探针)")
            sys.exit(1)
        
        baseline_gbps = median(before_fault)
        print(f"\n自动计算基线带宽: {baseline_gbps:.2f} GB/s (中位数, n={len(before_fault)})")
    else:
        print(f"\n使用指定基线带宽: {baseline_gbps:.2f} GB/s")

    degradation_threshold_gbps = baseline_gbps * threshold
    print(f"带宽下降判定阈值: < {degradation_threshold_gbps:.2f} GB/s (基线 × {threshold})")

    # 2. 标记每个探针: 是否异常
    for p in bw_probes:
        p["is_degraded"] = p["bandwidth_gbps"] < degradation_threshold_gbps

    # 3. 检测延迟 (仅限有时间戳)
    detection_latency = None
    first_detection_t = None
    if has_ts and fault_start is not None:
        # 连续 detect_window 次低带宽才确认
        consecutive_count = 0
        for p in bw_probes:
            if p["t"] >= fault_start:
                if p["is_degraded"]:
                    consecutive_count += 1
                    if consecutive_count >= detect_window:
                        first_detection_t = p["t"]
                        detection_latency = first_detection_t - fault_start
                        break
                else:
                    consecutive_count = 0
        
        if detection_latency is not None:
            print(f"\n✓ 检测延迟: {detection_latency:.2f} 秒")
            print(f"  (故障开始 {fault_start:.2f} → 首次检测 {first_detection_t:.2f})")
        else:
            print("\n✗ 未检测到故障 (在日志范围内)")
    
    # 4. 召回率 (故障期间标记为异常的比例)
    recall = None
    precision = None
    if has_ts and fault_start is not None and fault_end is not None:
        during_fault = [p for p in bw_probes if fault_start <= p["t"] <= fault_end]
        if len(during_fault) > 0:
            detected_count = sum(1 for p in during_fault if p["is_degraded"])
            recall = detected_count / len(during_fault)
            print(f"\n召回率: {recall:.2%} ({detected_count}/{len(during_fault)} 探针)")
        
        # 精确率 (标记为异常的探针中, 真正在故障期间的比例)
        flagged = [p for p in bw_probes if p["is_degraded"]]
        if len(flagged) > 0:
            true_positives = sum(1 for p in flagged if fault_start <= p["t"] <= fault_end)
            precision = true_positives / len(flagged)
            print(f"精确率: {precision:.2%} ({true_positives}/{len(flagged)} 探针)")
    
    # 5. 带宽 time series 统计
    degraded_probes = [p for p in bw_probes if p["is_degraded"]]
    if len(degraded_probes) > 0:
        print(f"\n异常探针数: {len(degraded_probes)} / {len(bw_probes)}")
        degraded_bw = [p["bandwidth_gbps"] for p in degraded_probes]
        print(f"  异常带宽范围: {min(degraded_bw):.2f} - {max(degraded_bw):.2f} GB/s")
        print(f"  异常带宽均值: {mean(degraded_bw):.2f} GB/s")

    # 6. 输出 JSON
    result = {
        "baseline_gbps": baseline_gbps,
        "threshold": threshold,
        "degradation_threshold_gbps": degradation_threshold_gbps,
        "total_bw_probes": len(bw_probes),
        "degraded_probes": len(degraded_probes),
        "detection_latency_sec": detection_latency,
        "recall": recall,
        "precision": precision,
        "fault_start": fault_start,
        "fault_end": fault_end,
        "has_timestamp": has_ts,
    }
    
    json_path = RESULTS_DIR / "fault_detection.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n结果已保存: {json_path}")

    # 7. 输出报告
    report_path = RESULTS_DIR / "fault_detection_report.txt"
    with open(report_path, "w") as f:
        f.write("# P0.4: 故障注入检测分析报告\n\n")
        f.write(f"**基线带宽**: {baseline_gbps:.2f} GB/s\n")
        f.write(f"**判定阈值**: < {degradation_threshold_gbps:.2f} GB/s (基线 × {threshold})\n\n")
        
        if detection_latency is not None:
            f.write(f"## 检测延迟\n\n{detection_latency:.2f} 秒\n\n")
        
        if recall is not None:
            f.write(f"## 召回率\n\n{recall:.2%}\n\n")
        if precision is not None:
            f.write(f"## 精确率\n\n{precision:.2%}\n\n")
        
        f.write(f"## 异常探针\n\n")
        f.write(f"- 总带宽探针: {len(bw_probes)}\n")
        f.write(f"- 异常探针: {len(degraded_probes)}\n")
        if len(degraded_probes) > 0:
            degraded_bw = [p["bandwidth_gbps"] for p in degraded_probes]
            f.write(f"- 异常带宽均值: {mean(degraded_bw):.2f} GB/s\n")
        
    print(f"报告已保存: {report_path}")

    # 8. 输出 time series CSV
    csv_path = RESULTS_DIR / "bandwidth_timeseries.csv"
    with open(csv_path, "w") as f:
        if has_ts:
            f.write("timestamp,path_id,bandwidth_gbps,is_degraded\n")
            for p in bw_probes:
                f.write(f"{p['t']:.3f},{p['path_id']},{p['bandwidth_gbps']:.2f},{int(p['is_degraded'])}\n")
        else:
            f.write("index,path_id,bandwidth_gbps,is_degraded\n")
            for i, p in enumerate(bw_probes):
                f.write(f"{i},{p['path_id']},{p['bandwidth_gbps']:.2f},{int(p['is_degraded'])}\n")
    print(f"Time series 已保存: {csv_path}")

    print("\n" + "=" * 60)
    print("分析完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
