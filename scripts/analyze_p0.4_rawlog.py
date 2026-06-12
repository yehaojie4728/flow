#!/usr/bin/env python3
"""
基于 p0.4_raw.log 的 WallStart_ns 时间戳，分析故障注入前/中/后的带宽变化。

用法:
  python scripts/analyze_p0.4_rawlog.py \
      --raw-log data/collected/p0.4_raw.log \
      --fault1-start "2026-06-12 00:11:02" --fault1-end "2026-06-12 00:16:13" \
      --fault2-start "2026-06-12 00:36:13" --fault2-end "2026-06-12 00:41:24"
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path
from statistics import median

RESULTS_DIR = Path(__file__).resolve().parent.parent / "code" / "results" / "p0.4_fault_detection"


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp()


def load_raw(path, exclude_injector=True):
    """
    加载 raw log，可选排除故障注入器的 memcpy。
    
    故障注入器特征：
    - Size_MB >= 100 (固定 128MB)
    - PID 3749335 (online_loop 探针)
    - PID >= 3763690 (故障注入器进程)
    """
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                pid = int(r["PID"])
                size_mb = float(r["Size_MB"])
                wall_ns = int(r["WallStart_ns"])
                bw = float(r["Bandwidth_GBps"])
                
                # 过滤掉故障注入器和探针的 memcpy
                if exclude_injector:
                    # 大块 memcpy (>= 100MB) 是故障注入器或探针
                    if size_mb >= 100:
                        continue
                    # 探针进程和注入器进程
                    if pid == 3749335 or pid >= 3763690:
                        continue
                
                rows.append((wall_ns / 1e9, bw))
            except (ValueError, KeyError):
                continue
    return rows  # list of (wall_sec, bw_gbps)


def stats(values):
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": round(sum(values) / len(values), 2),
        "median": round(median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def analyze_window(rows, start_ts, end_ts):
    return [bw for (t, bw) in rows if start_ts <= t <= end_ts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-log", required=True)
    ap.add_argument("--fault1-start", required=True)
    ap.add_argument("--fault1-end", required=True)
    ap.add_argument("--fault2-start", required=True)
    ap.add_argument("--fault2-end", required=True)
    args = ap.parse_args()

    rows = load_raw(args.raw_log)
    if not rows:
        print("ERROR: raw log empty or unreadable")
        return

    f1s, f1e = parse_ts(args.fault1_start), parse_ts(args.fault1_end)
    f2s, f2e = parse_ts(args.fault2_start), parse_ts(args.fault2_end)

    # 基线：第1次注入前
    baseline_bw = [bw for (t, bw) in rows if t < f1s]
    # 第1次注入期间
    fault1_bw = analyze_window(rows, f1s, f1e)
    # 两次注入之间
    between_bw = analyze_window(rows, f1e, f2s)
    # 第2次注入期间
    fault2_bw = analyze_window(rows, f2s, f2e)
    # 第2次注入之后
    post_bw = [bw for (t, bw) in rows if t > f2e]

    baseline_stats = stats(baseline_bw)
    base_median = baseline_stats["median"] or 1.0

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / "rawlog_analysis_report.txt"

    lines = []
    lines.append("# P0.4 Raw Log 带宽分析报告")
    lines.append(f"总记录数: {len(rows)}")
    lines.append(f"时间范围: {datetime.fromtimestamp(rows[0][0])} ~ {datetime.fromtimestamp(rows[-1][0])}")
    lines.append("")

    for label, s in [
        ("基线（注入前）", baseline_stats),
        ("第1次注入期间（轻度, 20ms）", stats(fault1_bw)),
        ("两次注入之间（恢复期）", stats(between_bw)),
        ("第2次注入期间（重度, 5ms）", stats(fault2_bw)),
        ("第2次注入之后", stats(post_bw)),
    ]:
        if s["n"] == 0:
            lines.append(f"## {label}: 无数据")
            continue
        drop = round((1 - s["median"] / base_median) * 100, 1) if s["median"] else None
        drop_str = f"，相对基线下降 {drop}%" if drop is not None and label != "基线（注入前）" else ""
        lines.append(f"## {label}")
        lines.append(f"  n={s['n']}, median={s['median']} GB/s, mean={s['mean']} GB/s, "
                     f"min={s['min']} GB/s, max={s['max']} GB/s{drop_str}")
        lines.append("")

    report = "\n".join(lines)
    print(report)
    report_path.write_text(report)
    print(f"\n报告已保存: {report_path}")


if __name__ == "__main__":
    main()
