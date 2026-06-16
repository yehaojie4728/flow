#!/usr/bin/env python3
"""Generate figures for P1.1, P1.3, P1.4, P2.1, P2.2, P2.3."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

ROOT    = Path("/root/FlowGap-work/FlowGap-paper/code")
RES     = ROOT / "results"
FIG_DIR = ROOT / "results" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = ["250µs", "500µs", "1ms"]
COLORS   = ["#1f77b4", "#ff7f0e", "#2ca02c"]

plt.rcParams.update({"font.size": 11, "axes.grid": True,
                     "grid.alpha": 0.3, "figure.dpi": 150})

# ─────────────────────────── P1.1 Feature Ablation ───────────────────────────
data = json.load(open(RES / "P1.1_ablation_study/ablation_study.json"))
df11 = pd.DataFrame(data)

baseline = df11[df11.ablation == "baseline"].set_index("horizon")
ablated  = df11[df11.ablation == "leave_one_group_out"]

groups = ablated["removed_group"].unique()
x = np.arange(len(groups))
w = 0.26

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for ax, metric, ylabel in zip(axes, ["precision", "fsr"],
                               ["Precision", "False Safe Rate"]):
    for i, (h, c) in enumerate(zip(HORIZONS, COLORS)):
        bl_val  = float(baseline.loc[h, metric])
        deltas  = []
        for g in groups:
            row = ablated[(ablated.removed_group == g) & (ablated.horizon == h)]
            val = float(row[metric].values[0]) if len(row) else bl_val
            deltas.append(val - bl_val)
        bars = ax.bar(x + i * w, deltas, w, label=h, color=c, alpha=0.85)
    ax.axhline(0, color="k", linewidth=0.8)
    ax.set_xticks(x + w)
    ax.set_xticklabels(groups, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(f"Δ {ylabel} vs baseline")
    ax.set_title(f"P1.1 Feature Ablation – Δ{ylabel}")
    ax.legend()

fig.tight_layout()
fig.savefig(FIG_DIR / "p1.1_feature_ablation.png")
plt.close(fig)
print("Saved p1.1_feature_ablation.png")

# ─────────────────────────── P1.3 eBPF Overhead ──────────────────────────────
d13 = json.load(open(RES / "P1.3_ebpf_overhead/overhead_analysis.json"))
pa  = d13["phase_a_baseline_busy_pct"]
pb  = d13["phase_b_traced_busy_pct"]
trc = d13["tracer_process_cpu_pct_per_core"]

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

# Left: box-like summary (mean±std, median) for Phase A vs B
ax = axes[0]
labels  = ["Phase A\n(baseline)", "Phase B\n(with tracer)"]
means   = [pa["mean"],   pb["mean"]]
medians = [pa["median"], pb["median"]]
stds    = [pa["stdev"],  pb["stdev"]]
xp = [0, 1]
ax.bar(xp, means, 0.4, color=["#1f77b4", "#ff7f0e"], alpha=0.75, label="Mean")
ax.errorbar(xp, means, yerr=stds, fmt="none", color="k", capsize=5, linewidth=1.5)
ax.scatter(xp, medians, color="red", zorder=5, s=60, label="Median")
ax.set_xticks(xp); ax.set_xticklabels(labels)
ax.set_ylabel("Host CPU busy (%)")
ax.set_title("P1.3 System CPU: Baseline vs Traced")
ax.legend()

# Right: tracer process CPU distribution (mean + median)
ax = axes[1]
cats = ["System Δ\n(mean)", "System Δ\n(median)", "Tracer process\n(system %)"]
vals = [d13["overhead"]["system_busy_delta_pp"],
        round(pb["median"] - pa["median"], 4),
        d13["overhead"]["tracer_process_system_pct"]]
bars = ax.bar(cats, vals, color=["#ff7f0e", "#d62728", "#9467bd"], alpha=0.85, width=0.45)
for bar, v in zip(bars, vals):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.002,
            f"{v:.4f}%", ha="center", va="bottom", fontsize=9)
ax.set_ylabel("CPU overhead (pp or %)")
ax.set_title("P1.3 eBPF Tracer Overhead Breakdown")

fig.tight_layout()
fig.savefig(FIG_DIR / "p1.3_ebpf_overhead.png")
plt.close(fig)
print("Saved p1.3_ebpf_overhead.png")

# ─────────────────────────── P1.4 Parameter Sensitivity ──────────────────────
df14 = pd.DataFrame(json.load(open(RES / "P1.4_param_sensitivity/param_sensitivity.json")))

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
ax = axes[0]
ax.plot(df14.eta_bw, df14.precision_500us, "o-", color="#1f77b4", label="Precision (500µs)")
ax.axvline(0.80, color="gray", linestyle="--", linewidth=1, label="η=0.80 (recommended)")
ax.set_xlabel("η_bw"); ax.set_ylabel("Precision"); ax.set_title("P1.4 η_bw vs Precision")
ax.legend(); ax.set_ylim(0.9, 1.01)

ax = axes[1]
ax.plot(df14.eta_bw, df14.bw_probes, "s-", color="#ff7f0e", label="BW probes")
ax.set_xlabel("η_bw"); ax.set_ylabel("Number of BW probes")
ax2 = ax.twinx()
ax2.plot(df14.eta_bw, df14.unsafe_count, "^--", color="#d62728", label="Unsafe probes")
ax2.set_ylabel("Unsafe probes", color="#d62728")
ax2.tick_params(axis="y", labelcolor="#d62728")
ax.axvline(0.80, color="gray", linestyle="--", linewidth=1)
ax.set_title("P1.4 η_bw vs Probes")
lines1, l1 = ax.get_legend_handles_labels()
lines2, l2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, l1 + l2)

fig.tight_layout()
fig.savefig(FIG_DIR / "p1.4_param_sensitivity.png")
plt.close(fig)
print("Saved p1.4_param_sensitivity.png")

# ─────────────────────────── P2.1 Cold Start ─────────────────────────────────
df21 = pd.read_csv(RES / "P2.1_cold_start/cold_start.csv")

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
for ax, metric, ylabel in zip(axes, ["precision", "fsr"], ["Precision", "FSR"]):
    for h, c in zip(HORIZONS, COLORS):
        sub = df21[df21.horizon == h]
        ax.semilogx(sub.warmup_k, sub[metric], "o-", color=c, label=h)
    ax.set_xlabel("Warm-up samples k (log scale)")
    ax.set_ylabel(ylabel)
    ax.set_title(f"P2.1 Cold-start – {ylabel} vs k")
    ax.legend()
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter())

fig.tight_layout()
fig.savefig(FIG_DIR / "p2.1_cold_start.png")
plt.close(fig)
print("Saved p2.1_cold_start.png")

# ─────────────────────────── P2.2 Drift ──────────────────────────────────────
df22d = pd.read_csv(RES / "P2.2_drift/drift_deciles.csv")
df22s = pd.read_csv(RES / "P2.2_drift/drift_split.csv")

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
ax = axes[0]
for h, c in zip(HORIZONS, COLORS):
    sub = df22d[df22d.horizon == h]
    ax.plot(sub.decile, sub.precision, "o-", color=c, label=h)
ax.set_xlabel("Pass 2 decile (chronological)")
ax.set_ylabel("Precision")
ax.set_title("P2.2 Drift – Precision per decile")
ax.set_xticks(range(1, 11))
ax.legend()

ax = axes[1]
xp    = np.arange(len(HORIZONS))
w     = 0.35
early = df22s["precision_first80"].values
late  = df22s["precision_last20"].values
ax.bar(xp - w/2, early, w, label="First 80%", color="#1f77b4", alpha=0.85)
ax.bar(xp + w/2, late,  w, label="Last 20%",  color="#ff7f0e", alpha=0.85)
ax.set_xticks(xp); ax.set_xticklabels(df22s.horizon)
ax.set_ylabel("Precision"); ax.set_title("P2.2 Drift – First 80% vs Last 20%")
ax.set_ylim(0.90, 1.01)
ax.legend()

fig.tight_layout()
fig.savefig(FIG_DIR / "p2.2_drift.png")
plt.close(fig)
print("Saved p2.2_drift.png")

# ─────────────────────────── P2.3 Oracle Gap ─────────────────────────────────
d23 = json.load(open(RES / "P2.3_oracle_gap/oracle_gap.json"))

fig, ax = plt.subplots(figsize=(6, 4.5))
policies = ["oracle", "flowgap_predictive"]
ratios   = [d23["oracle"]["safe_probing_ratio"],
            d23["flowgap_predictive"]["safe_probing_ratio"]]
probes   = [d23["oracle"]["total_probes"],
            d23["flowgap_predictive"]["total_probes"]]
colors   = ["#2ca02c", "#1f77b4"]
bars = ax.bar(policies, ratios, color=colors, alpha=0.85, width=0.4)
for bar, r, n in zip(bars, ratios, probes):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.002,
            f"{r:.4f}\n({n} probes)", ha="center", va="bottom", fontsize=9)
ax.set_ylim(0.95, 1.02)
ax.set_ylabel("safe_probing_ratio")
ax.set_title(f"P2.3 Oracle Gap\n(oracle − flowgap = {d23['oracle_gap']:+.4f})")
fig.tight_layout()
fig.savefig(FIG_DIR / "p2.3_oracle_gap.png")
plt.close(fig)
print("Saved p2.3_oracle_gap.png")

print(f"\nAll figures saved to {FIG_DIR}")
