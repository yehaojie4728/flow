#!/usr/bin/env python3
"""
Generate publication-ready figures for FlowGap paper (SoCC 2026 submission).

This script creates ACM sigconf-style figures from P0 experiment results.
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from pathlib import Path

# ACM sigconf column widths (in inches)
ACM_SINGLE_COLUMN_WIDTH = 3.33  # Single column
ACM_DOUBLE_COLUMN_WIDTH = 7.0   # Double column (full page width)

# High-saturation colorblind-friendly palette (enhanced Okabe-Ito)
OKABE_ITO = [
    '#FF9500',  # Vibrant Orange
    '#56B4E9',  # Sky Blue
    '#00D084',  # Vibrant Green
    '#FFD700',  # Gold Yellow
    '#0066CC',  # Vivid Blue
    '#FF4500',  # Vivid Red-Orange
    '#E040FB',  # Vivid Purple
    '#000000'   # Black
]


def setup_publication_style():
    """Configure matplotlib for ACM publication quality."""
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
        'font.size': 9,
        'axes.labelsize': 9,
        'axes.titlesize': 9,
        'xtick.labelsize': 8,
        'ytick.labelsize': 8,
        'legend.fontsize': 8,
        'figure.titlesize': 10,
        'axes.linewidth': 0.8,
        'grid.linewidth': 0.5,
        'lines.linewidth': 1.5,
        'patch.linewidth': 0.5,
        'xtick.major.width': 0.8,
        'ytick.major.width': 0.8,
        'xtick.major.size': 3.5,
        'ytick.major.size': 3.5,
        'pdf.fonttype': 42,  # TrueType fonts for editability
        'ps.fonttype': 42,
        'axes.prop_cycle': plt.cycler(color=OKABE_ITO)
    })


def figure1_policy_comparison():
    """
    Figure 1: Policy Comparison - Safety, BW Probes, and Overhead.
    
    Creates a grouped bar chart comparing 5 probing policies on key metrics.
    Uses ACM double-column width for clarity.
    
    Key insight: FlowGap achieves 100% safety with high BW probe count,
    while random has 45.8% unsafe rate despite fewer BW probes.
    """
    print("Generating Figure 1: Policy Comparison...")
    
    # Load data
    df = pd.read_csv('../results/p0.1_v2_probe_coverage/comparison.csv')
    
    # Select key policies for figure (now 6 policies including threshold)
    policies_to_show = ['no_probing', 'fixed_interval', 'random', 
                        'threshold', 'flowgap_predictive', 'oracle']
    policy_labels = {
        'no_probing': 'No Probing',
        'fixed_interval': 'Fixed Interval',
        'random': 'Random',
        'threshold': 'Threshold',
        'flowgap_predictive': 'FlowGap',
        'oracle': 'Oracle'
    }
    
    df_subset = df[df['policy'].isin(policies_to_show)].copy()
    df_subset['policy_label'] = df_subset['policy'].map(policy_labels)
    
    # Calculate correct metrics
    df_subset['safe_rate_pct'] = 100.0 - df_subset['unsafe_rate_pct']
    # Use absolute BW probe count (in thousands)
    df_subset['bw_probes_k'] = df_subset['bw_probes'] / 1000.0
    
    # Define hatch patterns for better distinction (6 policies)
    hatches = ['', '///', 'xxx', '|||', '...', '\\\\\\']
    
    # Create figure with 3 subplots
    fig, axes = plt.subplots(1, 3, figsize=(ACM_DOUBLE_COLUMN_WIDTH, 2.2))
    
    x = np.arange(len(policies_to_show))
    width = 0.6
    
    # Subplot A: Safety Rate
    ax = axes[0]
    colors_a = [OKABE_ITO[0], OKABE_ITO[0], OKABE_ITO[5], OKABE_ITO[3], OKABE_ITO[4], OKABE_ITO[2]]
    for i, (xi, val, hatch, color) in enumerate(zip(x, df_subset['safe_rate_pct'], hatches, colors_a)):
        ax.bar(xi, val, width, color=color, edgecolor='black', 
               linewidth=0.8, hatch=hatch)
    
    ax.set_ylabel('Safety Rate (%)', fontsize=9)
    ax.set_ylim([0, 110])
    ax.set_xticks(x)
    ax.set_xticklabels(df_subset['policy_label'], fontsize=7, rotation=30, ha='right')
    ax.axhline(y=100, color='gray', linestyle='--', linewidth=0.8, alpha=0.6)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    # Subplot B: BW Probe Count (in thousands)
    ax = axes[1]
    colors_b = [OKABE_ITO[1], OKABE_ITO[1], OKABE_ITO[5], OKABE_ITO[3], OKABE_ITO[4], OKABE_ITO[2]]
    for i, (xi, val, hatch, color) in enumerate(zip(x, df_subset['bw_probes_k'], hatches, colors_b)):
        ax.bar(xi, val, width, color=color, edgecolor='black', 
               linewidth=0.8, hatch=hatch)
    
    ax.set_ylabel('BW Probes (×1000)', fontsize=9)
    ax.set_ylim([0, 60])
    ax.set_xticks(x)
    ax.set_xticklabels(df_subset['policy_label'], fontsize=7, rotation=30, ha='right')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    # Subplot C: Overhead
    ax = axes[2]
    colors_c = [OKABE_ITO[6], OKABE_ITO[6], OKABE_ITO[5], OKABE_ITO[3], OKABE_ITO[4], OKABE_ITO[2]]
    for i, (xi, val, hatch, color) in enumerate(zip(x, df_subset['overhead_pct'], hatches, colors_c)):
        ax.bar(xi, val, width, color=color, edgecolor='black', 
               linewidth=0.8, hatch=hatch)
    
    ax.set_ylabel('Overhead (%)', fontsize=9)
    ax.set_ylim([0, 6])
    ax.set_xticks(x)
    ax.set_xticklabels(df_subset['policy_label'], fontsize=7, rotation=30, ha='right')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    plt.tight_layout()
    
    # Save in multiple formats
    output_dir = Path('../results/figures')
    output_dir.mkdir(exist_ok=True)
    
    fig.savefig(output_dir / 'fig1_policy_comparison.pdf', 
                dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'fig1_policy_comparison.png', 
                dpi=300, bbox_inches='tight')
    
    print(f"  ✓ Saved to {output_dir / 'fig1_policy_comparison.pdf'}")
    print(f"  Key insight: FlowGap = 100% safe + 37.9K BW probes vs Random = 54.2% safe + 0.5K BW probes")
    plt.close()


def figure2_calibration():
    """
    Figure 2: Model Calibration - Reliability Curve.
    
    Shows predicted confidence vs actual accuracy for 3 probe horizons.
    Uses ACM single-column width.
    """
    print("Generating Figure 2: Calibration Curve...")
    
    # Load data
    df = pd.read_csv('../results/p0.2.2_calibration/reliability_curve_data.csv')
    
    # Filter out empty bins
    df_plot = df[df['count'] > 0].copy()
    
    fig, ax = plt.subplots(figsize=(ACM_SINGLE_COLUMN_WIDTH, 2.8))
    
    horizons = [
        (500000, '500µs (NORMAL)', OKABE_ITO[0], 'o'),
        (5100000, '5.1ms (BW)', OKABE_ITO[1], 's')
    ]
    
    # Plot perfect calibration line
    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.5, label='Perfect calibration')
    
    # Plot each horizon
    for horizon_ns, label, color, marker in horizons:
        subset = df_plot[df_plot['horizon_ns'] == horizon_ns]
        if len(subset) > 0:
            ax.plot(subset['confidence'], subset['accuracy'], 
                   marker=marker, markersize=5, linewidth=1.5,
                   color=color, label=label, alpha=0.8)
    
    ax.set_xlabel('Predicted Confidence')
    ax.set_ylabel('Actual Accuracy')
    ax.set_xlim([-0.05, 1.05])
    ax.set_ylim([-0.05, 1.05])
    ax.legend(loc='lower right', frameon=False, fontsize=7)
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.set_aspect('equal')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    plt.tight_layout()
    
    output_dir = Path('../results/figures')
    output_dir.mkdir(exist_ok=True)
    
    fig.savefig(output_dir / 'fig2_calibration.pdf', 
                dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'fig2_calibration.png', 
                dpi=300, bbox_inches='tight')
    
    print(f"  ✓ Saved to {output_dir / 'fig2_calibration.pdf'}")
    plt.close()


def figure3_overhead_breakdown():
    """
    Figure 3: Probe Overhead Breakdown.
    
    Shows the composition of probe overhead (LAT vs BW probes).
    Uses ACM single-column width.
    """
    print("Generating Figure 3: Overhead Breakdown...")
    
    # Load data
    with open('../results/p0.3_training_overhead/overhead_analysis.json', 'r') as f:
        data = json.load(f)
    
    lat_count = data['probe_breakdown']['latency_probes']
    bw_count = data['probe_breakdown']['bandwidth_probes']
    lat_time = lat_count * data['probe_timing']['avg_latency_probe_us'] / 1e6
    bw_time = bw_count * data['probe_timing']['avg_bandwidth_probe_us'] / 1e6
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(ACM_DOUBLE_COLUMN_WIDTH * 0.7, 2.2))
    
    # Panel A: Probe count breakdown
    ax = ax1
    counts = [lat_count, bw_count]
    labels = ['LAT Probes\n(385)', 'BW Probes\n(103)']
    colors = [OKABE_ITO[0], OKABE_ITO[1]]
    
    wedges, texts, autotexts = ax.pie(counts, labels=labels, autopct='%1.1f%%',
                                        colors=colors, startangle=90,
                                        textprops={'fontsize': 8})
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    ax.set_title('Probe Count', fontsize=9, pad=10)
    ax.text(-0.25, 1.15, 'A', transform=ax.transAxes,
            fontsize=11, fontweight='bold', va='top')
    
    # Panel B: Time breakdown
    ax = ax2
    times = [lat_time, bw_time]
    labels = [f'LAT Time\n({lat_time:.3f}s)', f'BW Time\n({bw_time:.3f}s)']
    
    wedges, texts, autotexts = ax.pie(times, labels=labels, autopct='%1.1f%%',
                                        colors=colors, startangle=90,
                                        textprops={'fontsize': 8})
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    ax.set_title('Probe Time', fontsize=9, pad=10)
    ax.text(-0.25, 1.15, 'B', transform=ax.transAxes,
            fontsize=11, fontweight='bold', va='top')
    
    # Add overall overhead annotation
    overhead_pct = data['overhead']['overhead_percentage']
    fig.text(0.5, 0.02, f'Total overhead: {overhead_pct:.4f}% of training time',
             ha='center', fontsize=8, style='italic')
    
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    
    output_dir = Path('../results/figures')
    output_dir.mkdir(exist_ok=True)
    
    fig.savefig(output_dir / 'fig3_overhead_breakdown.pdf', 
                dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'fig3_overhead_breakdown.png', 
                dpi=300, bbox_inches='tight')
    
    print(f"  ✓ Saved to {output_dir / 'fig3_overhead_breakdown.pdf'}")
    plt.close()


def main():
    """Generate all figures for the paper."""
    print("=" * 60)
    print("FlowGap Figure Generation for SoCC 2026")
    print("=" * 60)
    
    setup_publication_style()
    
    figure1_policy_comparison()
    figure2_calibration()
    figure3_overhead_breakdown()
    
    print("=" * 60)
    print("✓ All figures generated successfully!")
    print("=" * 60)


if __name__ == '__main__':
    main()
