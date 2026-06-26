#!/usr/bin/env python3
"""
Generate D1-D3 figures for FlowGap SoCC 2026 paper.
Publication-ready: colorblind-safe palette, 300dpi, PDF+PNG output.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUT_DIR = "/root/FlowGap-work/FlowGap-paper/code/results/figures"

# ── Colorblind-safe palette (Okabe-Ito) ──
C_RED    = '#D55E00'
C_BLUE   = '#0072B2'
C_GREEN  = '#009E73'
C_ORANGE = '#E69F00'
C_PURPLE = '#CC79A7'
C_GRAY   = '#888888'

# ── Global style ──
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
    'font.size': 9,
    'axes.labelsize': 10,
    'axes.titlesize': 11,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'legend.fontsize': 8,
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'axes.spines.top': False,
    'axes.spines.right': False,
})

# ====================================================================
# FIG D1: Motivation — fixed_interval vs FlowGap Unsafe%
# ====================================================================

def fig_d1():
    strategies = ['fixed (1ms)', 'fixed (5ms)', 'FlowGap']
    unsafe_pct = [93.9, 77.8, 0.0]
    colors    = [C_ORANGE, C_ORANGE, C_GREEN]
    hatch     = ['/', '\\', '']
    
    fig, ax = plt.subplots(figsize=(4.5, 2.8))
    bars = ax.bar(strategies, unsafe_pct, color=colors, edgecolor='black', linewidth=0.8)
    
    # Add hatch patterns to fixed-interval bars
    for b, h in zip(bars[:2], hatch[:2]):
        b.set_hatch(h)
    
    # Value labels
    for bar, val in zip(bars, unsafe_pct):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                f'{val:.1f}%', ha='center', va='bottom', fontweight='bold', fontsize=10)
    
    ax.set_ylabel('Unsafe Probe Rate (%)')
    ax.set_ylim(0, 110)
    ax.set_title('Probe Collision Rate on Densest D2H Path\n(50 ms, 86.4% busy fraction)',
                 fontsize=10, fontweight='bold')
    
    # Annotation
    ax.annotate('Blind probing:\n78\u201394% collision', xy=(0.5, 70), fontsize=8,
                ha='center', color=C_RED, fontstyle='italic',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    ax.annotate('FlowGap:\n0% collision,\n0 probes placed\n(chooses silence)', xy=(2, 20), fontsize=8,
                ha='center', color=C_GREEN, fontstyle='italic',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    fig.savefig(f'{OUT_DIR}/fig_d1_motivation.pdf')
    fig.savefig(f'{OUT_DIR}/fig_d1_motivation.png')
    plt.close(fig)
    print("Saved: fig_d1_motivation.{pdf,png}")

# ====================================================================
# FIG D2: Drift gap distribution — first 80% vs last 20%
# ====================================================================

def fig_d2():
    fig, axes = plt.subplots(1, 2, figsize=(7, 3.2))
    
    # ── Left: Gap CDF ──
    ax = axes[0]
    # Reconstruct approximate CDF from percentile data
    # early: p10=167, p25=176, p50=208, p75=4103, p90=18029 (µs)
    # late:  p10=163, p25=169, p50=189, p75=10518, p90=18095 (µs)
    percentiles = [10, 25, 50, 75, 90]
    early_vals  = np.array([167, 176, 208, 4103, 18029]) / 1000  # ms
    late_vals   = np.array([163, 169, 189, 10518, 18095]) / 1000
    
    # Smooth CDF via interpolation
    x_smooth = np.logspace(-1, 2, 200)  # 0.1ms to 100ms
    
    # Generate smooth CDF by interpolating
    early_cdf = np.interp(np.log10(x_smooth), np.log10(early_vals), np.array(percentiles)/100)
    late_cdf  = np.interp(np.log10(x_smooth), np.log10(late_vals),  np.array(percentiles)/100)
    
    ax.plot(x_smooth, early_cdf, color=C_BLUE, linewidth=2, label='First 80%')
    ax.plot(x_smooth, late_cdf,  color=C_RED, linewidth=2, label='Last 20%')
    ax.scatter(early_vals, np.array(percentiles)/100, color=C_BLUE, s=30, zorder=5, edgecolors='white', linewidth=0.5)
    ax.scatter(late_vals,  np.array(percentiles)/100, color=C_RED,  s=30, zorder=5, edgecolors='white', linewidth=0.5)
    
    ax.set_xscale('log')
    ax.set_xlabel('Gap Duration (ms)')
    ax.set_ylabel('CDF')
    ax.set_title('Gap Duration Distribution', fontweight='bold')
    ax.legend(frameon=False)
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.3, which='major')
    
    # ── Right: Safe Fraction per horizon ──
    ax = axes[1]
    horizons = ['50µs', '100µs', '250µs', '500µs', '1ms', '5.1ms', '10ms']
    early_safe = [100, 100, 31.8, 28.9, 28.9, 24.7, 17.4]
    late_safe  = [100, 100, 34.8, 34.0, 34.0, 29.9, 25.2]
    
    x = np.arange(len(horizons))
    w = 0.35
    bars1 = ax.bar(x - w/2, early_safe, w, color=C_BLUE, alpha=0.7, edgecolor='black', linewidth=0.5, label='First 80%')
    bars2 = ax.bar(x + w/2, late_safe,  w, color=C_RED,  alpha=0.7, edgecolor='black', linewidth=0.5, label='Last 20%',
                   hatch='///')
    
    # Delta labels
    for i, (e, l) in enumerate(zip(early_safe, late_safe)):
        delta = l - e
        if abs(delta) > 0.5:
            ax.annotate(f'+{delta:.1f}pp', xy=(i, max(e, l) + 3), ha='center', fontsize=7,
                        color=C_RED if delta > 0 else C_GREEN)
    
    ax.set_xticks(x)
    ax.set_xticklabels(horizons, rotation=30, ha='right')
    ax.set_ylabel('Safe Fraction (%)')
    ax.set_title('Per-Horizon Safe Fraction', fontweight='bold')
    ax.legend(frameon=False, loc='upper right', fontsize=7)
    ax.set_ylim(0, 115)
    
    plt.tight_layout()
    fig.savefig(f'{OUT_DIR}/fig_d2_drift_gap.pdf')
    fig.savefig(f'{OUT_DIR}/fig_d2_drift_gap.png')
    plt.close(fig)
    print("Saved: fig_d2_drift_gap.{pdf,png}")

# ====================================================================
# FIG D3-A: Forward ablation — Keep-Only each group
# ====================================================================

def fig_d3a():
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    
    groups = ['gap_stats\n(7d)', 'burst_stats\n(5d)', 'idle_age\n(1d)',
              'path_id\n(3d)', 'stream\n(3d)', 'phase\n(2d)',
              'resource\n(3d)', 'data_qual\n(4d)', 'time\n(2d)']
    
    fwd_250 = [0.9787, 0.9248, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    fwd_500 = [0.9642, 0.9131, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    fwd_1ms = [0.9634, 0.9132, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    baseline_prec = [0.9787, 0.9642, 0.9634]
    
    x = np.arange(len(groups))
    w = 0.25
    
    ax.bar(x - w, fwd_250, w, color=C_BLUE, alpha=0.7, edgecolor='black', linewidth=0.3, label='250µs')
    ax.bar(x,     fwd_500, w, color=C_ORANGE, alpha=0.7, edgecolor='black', linewidth=0.3, label='500µs')
    ax.bar(x + w, fwd_1ms, w, color=C_GREEN, alpha=0.7, edgecolor='black', linewidth=0.3, label='1ms')
    
    for b_p, c in zip(baseline_prec, [C_BLUE, C_ORANGE, C_GREEN]):
        ax.axhline(y=b_p, color=c, linestyle='--', linewidth=1, alpha=0.5)
    
    ax.set_xticks(x)
    ax.set_xticklabels(groups, rotation=40, ha='right', fontsize=7)
    ax.set_ylabel('Precision')
    ax.set_title('Forward Ablation (Keep-Only Each Group)', fontweight='bold')
    ax.legend(frameon=False, fontsize=7, loc='upper right', ncol=3)
    ax.set_ylim(0, 1.05)
    ax.grid(axis='y', alpha=0.3)
    
    ax.annotate('gap_stats alone\nmatches baseline\n(\u0394P=\u22120.0002)', xy=(-0.5, 0.98), fontsize=7,
                ha='left', color=C_BLUE, fontstyle='italic')
    ax.annotate('burst_stats\npartial signal', xy=(0.6, 0.88), fontsize=7,
                ha='left', color=C_ORANGE, fontstyle='italic')
    ax.annotate('7 groups: zero\nstandalone value', xy=(3, 0.08), fontsize=7,
                ha='left', color=C_GRAY, fontstyle='italic')
    
    plt.tight_layout()
    fig.savefig(f'{OUT_DIR}/fig_d3a_forward_ablation.pdf')
    fig.savefig(f'{OUT_DIR}/fig_d3a_forward_ablation.png')
    plt.close(fig)
    print("Saved: fig_d3a_forward_ablation.{pdf,png}")

# ====================================================================
# FIG D3-B: LOO — Leave-One-Group-Out
# ====================================================================

def fig_d3b():
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    
    groups = ['gap_stats\n(7d)', 'burst_stats\n(5d)', 'idle_age\n(1d)',
              'path_id\n(3d)', 'stream\n(3d)', 'phase\n(2d)',
              'resource\n(3d)', 'data_qual\n(4d)', 'time\n(2d)']
    
    loo_250 = [0.9263, 0.9787, 0.9787, 0.9787, 0.9787, 0.9787, 0.9787, 0.9787, 0.9787]
    loo_500 = [0.9131, 0.9642, 0.9642, 0.9642, 0.9642, 0.9642, 0.9642, 0.9642, 0.9642]
    loo_1ms = [0.9128, 0.9634, 0.9634, 0.9634, 0.9634, 0.9634, 0.9634, 0.9634, 0.9634]
    baseline_prec = [0.9787, 0.9642, 0.9634]
    
    x = np.arange(len(groups))
    w = 0.25
    
    ax.bar(x - w, loo_250, w, color=C_BLUE, alpha=0.7, edgecolor='black', linewidth=0.3, label='250µs')
    ax.bar(x,     loo_500, w, color=C_ORANGE, alpha=0.7, edgecolor='black', linewidth=0.3, label='500µs')
    ax.bar(x + w, loo_1ms, w, color=C_GREEN, alpha=0.7, edgecolor='black', linewidth=0.3, label='1ms')
    
    for b_p, c in zip(baseline_prec, [C_BLUE, C_ORANGE, C_GREEN]):
        ax.axhline(y=b_p, color=c, linestyle='--', linewidth=1, alpha=0.5)
    
    ax.set_xticks(x)
    ax.set_xticklabels(groups, rotation=40, ha='right', fontsize=7)
    ax.set_ylabel('Precision')
    ax.set_title('Leave-One-Group-Out (Remove Each Group)', fontweight='bold')
    ax.legend(frameon=False, fontsize=7, loc='upper right', ncol=3)
    ax.set_ylim(0.80, 1.05)
    ax.grid(axis='y', alpha=0.3)
    
    ax.annotate('Removing gap_stats:\nprecision drops\n5.2pp (0.965\u21920.913)', xy=(5, 0.85),
                fontsize=7, ha='center', color=C_RED, fontstyle='italic',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    fig.savefig(f'{OUT_DIR}/fig_d3b_loo_ablation.pdf')
    fig.savefig(f'{OUT_DIR}/fig_d3b_loo_ablation.png')
    plt.close(fig)
    print("Saved: fig_d3b_loo_ablation.{pdf,png}")

# ====================================================================
# ====================================================================
# Legacy D3 (kept for backward compatibility, not regenerated)
# ====================================================================

def fig_d3():
    """Old combined panel — use fig_d3a() and fig_d3b() instead."""
    pass


# ====================================================================
# FIG D4: Per-Horizon LOO Ablation heatmap
# ====================================================================

def fig_d4():
    horizons = ['50µs', '100µs', '250µs', '500µs', '1ms', '5.1ms']
    groups = ['gap', 'burst', 'idle', 'path', 'stream', 'phase', 'resource', 'qual', 'time']
    group_labels = ['gap_stats', 'burst_stats', 'idle_age', 'path_id', 'stream', 'phase',
                    'resource', 'data_qual', 'time']
    # ΔP matrix: row=horizon, col=group. Positive = worse than baseline.
    # baseline: [1.0, 1.0, 0.9787, 0.9642, 0.9634, 0.9246]
    delta = np.array([
        [0,0,0,0,0,0,0,0,0],           # 50µs
        [0,0,0,0,0,0,0,0,0],           # 100µs
        [0.0524,0,0,0,0,0,0,0,0],      # 250µs
        [0.0511,0,0,0,0,0,0,0,0],      # 500µs
        [0.0506,0,0,0,0,0,0,0,0],      # 1ms
        [0.0925,0.0009,0,0,0,0,0,0,0], # 5.1ms
    ])

    fig, ax = plt.subplots(figsize=(7, 3.0))

    im = ax.imshow(delta, cmap='YlOrRd', aspect='auto', vmin=0, vmax=0.1)

    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(group_labels, rotation=40, ha='right', fontsize=7)
    ax.set_yticks(range(len(horizons)))
    ax.set_yticklabels(horizons, fontsize=8)

    for i in range(len(horizons)):
        for j in range(len(groups)):
            v = delta[i, j]
            color = 'white' if v > 0.03 else 'black'
            ax.text(j, i, f'{v:.4f}' if v > 0 else '0', ha='center', va='center',
                    fontsize=6.5, color=color)

    cbar = plt.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
    cbar.set_label('Precision Drop (ΔP)', fontsize=8)
    ax.set_title('Per-Horizon LOO Ablation — gap_stats Dominance Across All Horizons',
                 fontweight='bold', fontsize=10)

    plt.tight_layout()
    fig.savefig(f'{OUT_DIR}/fig_d4_horizon_ablation.pdf')
    fig.savefig(f'{OUT_DIR}/fig_d4_horizon_ablation.png')
    plt.close(fig)
    print("Saved: fig_d4_horizon_ablation.{pdf,png}")


# ====================================================================
# FIG D5: Model comparison — EWMA / LR / GBDT
# ====================================================================

def fig_d5():
    horizons = ['250µs', '500µs', '1ms', '5.1ms']
    ewma =  [0.3242, 0.2995, 0.2988, 0.2574]
    lr =    [0.9285, 0.8788, 0.8779, 0.7765]
    gbdt =  [0.9722, 0.9647, 0.9660, 0.9636]

    x = np.arange(len(horizons))
    w = 0.25

    fig, ax = plt.subplots(figsize=(6, 3.2))

    ax.bar(x - w, ewma, w, color=C_GRAY,  alpha=0.7, edgecolor='black', linewidth=0.3, label='EWMA')
    ax.bar(x,     lr,   w, color=C_BLUE, alpha=0.7, edgecolor='black', linewidth=0.3, label='LogisticRegression')
    ax.bar(x + w, gbdt, w, color=C_GREEN, alpha=0.9, edgecolor='black', linewidth=0.3, label='GBDT')

    # Value labels
    for i in range(len(horizons)):
        for vals, offset, c in [(ewma, -w, C_GRAY), (lr, 0, C_BLUE), (gbdt, +w, C_GREEN)]:
            ypos = vals[i] + 0.02
            ax.text(i + offset, ypos, f'{vals[i]:.3f}', ha='center', fontsize=6, color=c,
                    rotation=90, va='bottom', fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(horizons, fontsize=9)
    ax.set_ylabel('Precision')
    ax.set_title('Model Comparison: EWMA vs LR vs GBDT', fontweight='bold', pad=35)
    ax.legend(frameon=False, fontsize=8, loc='upper center', ncol=3,
              bbox_to_anchor=(0.5, 1.12))
    ax.set_ylim(0, 1.08)
    ax.grid(axis='y', alpha=0.3)

    ax.annotate('GBDT >> LR:\n+4~19pp precision\n→ nonlinear patterns\nrequire trees',
                xy=(2.3, 0.62), fontsize=7, ha='center', color=C_RED, fontstyle='italic',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.85))

    plt.tight_layout()
    fig.savefig(f'{OUT_DIR}/fig_d5_model_comparison.pdf')
    fig.savefig(f'{OUT_DIR}/fig_d5_model_comparison.png')
    plt.close(fig)
    print("Saved: fig_d5_model_comparison.{pdf,png}")


# ====================================================================
# FIG D7: True cold-start — precision vs k (Pass1→Pass2)
# ====================================================================

def fig_d7():
    ks = [1, 5, 10, 50, 100, 200, 500, 1000, 2000, 5000]
    p250 = [0.3242, 0.3242, 0.7488, 0.7039, 0.5904, 0.8747, 0.8889, 0.9218, 0.8915, 0.9780]
    p500 = [0.2995, 0.2995, 0.7184, 0.6737, 0.5661, 0.9664, 0.9161, 0.9241, 0.8896, 0.9738]
    p1ms = [0.2988, 0.2988, 0.7184, 0.6736, 0.5661, 0.9664, 0.9153, 0.9233, 0.8888, 0.9738]

    fig, ax = plt.subplots(figsize=(6.5, 3.5))

    ax.plot(ks, p250, 'o-', color=C_BLUE, linewidth=1.8, markersize=5, label='250µs')
    ax.plot(ks, p500, 's-', color=C_ORANGE, linewidth=1.8, markersize=5, label='500µs (NORMAL)')
    ax.plot(ks, p1ms, '^-', color=C_GREEN, linewidth=1.8, markersize=5, label='1ms')

    ax.set_xscale('log')
    ax.set_xlabel('Training Samples (k) from Pass1')
    ax.set_ylabel('Precision on Pass2')
    ax.set_title('True Cold-Start: Pass1 → Pass2 Cross-Pass Generalization', fontweight='bold')
    ax.legend(frameon=False, fontsize=8, loc='lower right')
    ax.set_ylim(0.2, 1.08)
    ax.grid(True, alpha=0.3)

    # 0.95 threshold
    ax.axhline(y=0.95, color=C_GRAY, linestyle='--', alpha=0.5, linewidth=1)

    # k=200 marker — orange text in empty region (k=40, y=0.45)
    ax.text(40, 0.45,
            'k=200: 500µs\nprecision 0.966',
            fontsize=7.5, color=C_ORANGE, fontweight='bold')
    ax.vlines(x=200, ymin=0.20, ymax=0.966, colors=C_ORANGE, linestyles='dotted',
              linewidth=0.8, alpha=0.4)

    # k=5000 marker — green text in empty region (k=2000, y=0.40)
    ax.text(2000, 0.40,
            'k=5000: all horizons\nprecision 0.974+',
            fontsize=7.5, color=C_GREEN, fontweight='bold')
    ax.vlines(x=5000, ymin=0.20, ymax=0.978, colors=C_GREEN, linestyles='dotted',
              linewidth=0.8, alpha=0.4)

    plt.tight_layout()
    fig.savefig(f'{OUT_DIR}/fig_d7_cold_start.pdf')
    fig.savefig(f'{OUT_DIR}/fig_d7_cold_start.png')
    plt.close(fig)
    print("Saved: fig_d7_cold_start.{pdf,png}")


# ====================================================================
# Run all
# ====================================================================
if __name__ == '__main__':
    fig_d1()
    fig_d2()
    fig_d3a()
    fig_d3b()
    fig_d4()
    fig_d5()
    fig_d7()
    print("\nAll figures saved to:", OUT_DIR)
