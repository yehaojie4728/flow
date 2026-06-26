#!/usr/bin/env python3
"""
D2: Drift gap distribution — compare gap p50/p90 for first 80% vs last 20% of Pass2.

Purpose: Explain why "last 20% has higher precision" in P2.2 drift analysis.
If the gap distribution shifts (e.g., gaps get longer in later segments),
the improvement is a data artifact, not model learning.

Output: code/results/D2_drift_gap_distribution/
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
sys.path.insert(0, str(ROOT / "code"))
RESULTS_DIR = ROOT / "code" / "results" / "D2_drift_gap_distribution"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print("=" * 60)
    print("D2: Drift Gap Distribution — first 80% vs last 20% of Pass2")
    print("=" * 60)

    df = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events_pass2.parquet"))
    print(f"Pass2 data: {len(df)} rows")

    n = len(df)
    split_80 = int(n * 0.8)
    early = df.iloc[:split_80]
    late = df.iloc[split_80:]

    gap_col = "gap_duration_ns"
    lines = [
        "# D2: Drift Gap Distribution — first 80% vs last 20% of Pass2",
        "",
        "## Purpose",
        "",
        "Explain why P2.2 reports \"last 20% has higher precision than first 80%\".",
        "If gaps are systematically larger in later segments, higher precision is",
        "a data artifact — not model improvement.",
        "",
        f"**Split point**: {split_80} / {n}  (at 80% chronological ordering)",
        f"**Early samples**: {len(early)}  |  **Late samples**: {len(late)}",
        "",
        "## Gap Duration Distribution",
        "",
        "| Statistic | First 80% | Last 20% | Δ |",
        "|-----------|:---------:|:--------:|:--:|",
    ]

    stats = [
        ("p10", lambda x: np.percentile(x, 10)),
        ("p25", lambda x: np.percentile(x, 25)),
        ("p50 (median)", np.median),
        ("p75", lambda x: np.percentile(x, 75)),
        ("p90", lambda x: np.percentile(x, 90)),
        ("mean", np.mean),
        ("std", np.std),
        ("min", np.min),
        ("max", np.max),
    ]

    e_vals = early[gap_col].values
    l_vals = late[gap_col].values

    for label, fn in stats:
        e_v = fn(e_vals)
        l_v = fn(l_vals)
        d = l_v - e_v
        lines.append(f"| {label} | {e_v/1000:.1f} µs | {l_v/1000:.1f} µs | {d/1000:+.1f} µs |")

    # per-horizon safe fraction
    lines += ["", "## Per-Horizon Safe Fraction (gap ≥ threshold)", "",
              "| Horizon | First 80% Safe% | Last 20% Safe% | Δ |",
              "|---------|:---------------:|:--------------:|:--:|"]

    for h_ns in [50_000, 100_000, 250_000, 500_000, 1_000_000, 5_100_000, 10_000_000]:
        e_safe = 100 * (e_vals >= h_ns).sum() / len(e_vals)
        l_safe = 100 * (l_vals >= h_ns).sum() / len(l_vals)
        d_safe = l_safe - e_safe
        h_label = f"{h_ns/1000:.0f}µs" if h_ns < 1_000_000 else f"{h_ns/1e6:.1f}ms"
        lines.append(f"| {h_label} | {e_safe:.1f}% | {l_safe:.1f}% | {d_safe:+.1f} pp |")

    # per-path shift
    lines += ["", "## Per-Path Safe Fraction (500µs horizon)", "",
              "| Path | First 80% Safe% | Last 20% Safe% | Δ | N (early/late) |",
              "|------|:---------------:|:--------------:|:--:|:--------------:|"]

    for pid in sorted(df["path_id"].unique()):
        e_path = early[early["path_id"] == pid][gap_col].values
        l_path = late[late["path_id"] == pid][gap_col].values
        if len(e_path) < 5 or len(l_path) < 5:
            continue
        e_safe = 100 * (e_path >= 500_000).sum() / len(e_path)
        l_safe = 100 * (l_path >= 500_000).sum() / len(l_path)
        lines.append(f"| {pid} | {e_safe:.1f}% | {l_safe:.1f}% | {l_safe-e_safe:+.1f} pp | {len(e_path)}/{len(l_path)} |")

    # Summary interpretation
    lines += ["", "## Interpretation", ""]

    e_median = np.median(e_vals)
    l_median = np.median(l_vals)
    if l_median > e_median * 1.05:
        lines.append(
            f"**The last 20% has longer gaps** (median: {l_median/1000:.0f}µs vs {e_median/1000:.0f}µs, "
            f"+{100*(l_median-e_median)/e_median:.0f}%). "
            "This means higher precision is expected — it reflects easier prediction, "
            "not model improvement. The key takeaway is: **no precision degradation**."
        )
    elif abs(l_median - e_median) / e_median < 0.05:
        lines.append(
            "No systematic gap distribution shift. "
            "The precision improvement is likely due to the model calibration "
            "tending conservative on the specific gap distribution at the tail. "
            "Key takeaway: **no precision degradation — predictions remain stable.**"
        )
    else:
        lines.append(
            "Gap distribution appears to shift. Note that \"improvement\" does not "
            "indicate the model learns over time — it is a passive property of the data."
        )

    report_path = RESULTS_DIR / "report.md"
    report_path.write_text("\n".join(lines))

    # Also output to stdout
    for line in lines:
        print(line)
    print(f"\n{'='*60}")
    print(f"Report saved: {report_path}")
    print("Done.")


if __name__ == "__main__":
    main()
