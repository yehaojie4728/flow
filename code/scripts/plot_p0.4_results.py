#!/usr/bin/env python3
"""
生成 P0.4 实验的发表级图表

创建三个主要图表：
1. Figure 1: 带宽时间序列（展示故障注入期间的带宽变化）
2. Figure 2: 召回率和精确率柱状图（两次注入的比较）
3. Figure 3: 检测延迟条形图（验证 < 10 秒目标）

输出目录: ../results/figures/
"""

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime
from pathlib import Path

# 设置发表级样式
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica'],
    'font.size': 8,
    'axes.labelsize': 9,
    'axes.titlesize': 10,
    'xtick.labelsize': 7,
    'ytick.labelsize': 7,
    'legend.fontsize': 7,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'axes.linewidth': 0.8,
    'grid.linewidth': 0.5,
    'lines.linewidth': 1.0,
})

# 使用 Okabe-Ito 色盲友好配色
COLORS = {
    'baseline': '#56B4E9',      # 蓝色
    'fault': '#D55E00',         # 橙红色
    'recovery': '#009E73',      # 绿色
    'threshold': '#E69F00',     # 橙色
    'anomaly': '#CC79A7',       # 粉色
}

# 路径配置
RESULTS_DIR = Path(__file__).parent.parent / "results"
DATA_DIR = RESULTS_DIR / "p0.4_fault_detection"
OUTPUT_DIR = RESULTS_DIR / "figures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 故障时间窗口（Unix 时间戳）
FAULT1_START = datetime(2026, 6, 12, 16, 34, 59).timestamp()
FAULT1_END = datetime(2026, 6, 12, 16, 45, 10).timestamp()
FAULT2_START = datetime(2026, 6, 12, 17, 5, 10).timestamp()
FAULT2_END = datetime(2026, 6, 12, 17, 15, 21).timestamp()


def load_data():
    """加载实验数据"""
    # 时间序列数据
    ts_df = pd.read_csv(DATA_DIR / "bandwidth_timeseries.csv")
    ts_df['time_relative'] = (ts_df['timestamp'] - ts_df['timestamp'].min()) / 60  # 转为相对分钟
    
    # 故障检测结果（第2次注入的JSON，包含完整结果）
    with open(DATA_DIR / "fault_detection.json") as f:
        results = json.load(f)
    
    return ts_df, results


def plot_bandwidth_timeseries(ts_df, results):
    """
    Figure 1: 带宽时间序列图
    展示：基线 → 第1次注入 → 恢复 → 第2次注入 → 恢复
    """
    fig, ax = plt.subplots(figsize=(7, 3))
    
    # 时间转换
    t0 = ts_df['timestamp'].min()
    ts_df['time_min'] = (ts_df['timestamp'] - t0) / 60
    
    fault1_start_min = (FAULT1_START - t0) / 60
    fault1_end_min = (FAULT1_END - t0) / 60
    fault2_start_min = (FAULT2_START - t0) / 60
    fault2_end_min = (FAULT2_END - t0) / 60
    
    # 绘制带宽曲线（每10个点平均，减少噪声）
    window = 10
    ts_smooth = ts_df.groupby(ts_df.index // window).agg({
        'time_min': 'mean',
        'bandwidth_gbps': 'mean'
    })
    
    ax.plot(ts_smooth['time_min'], ts_smooth['bandwidth_gbps'], 
            color=COLORS['baseline'], linewidth=1.0, alpha=0.7, label='Measured Bandwidth')
    
    # 标记故障注入期间（背景阴影）
    ax.axvspan(fault1_start_min, fault1_end_min, alpha=0.2, 
               color=COLORS['fault'], label='Fault Injection (1ms)')
    ax.axvspan(fault2_start_min, fault2_end_min, alpha=0.2, 
               color=COLORS['fault'])
    
    # 绘制阈值线
    threshold = results['degradation_threshold_gbps']
    ax.axhline(threshold, color=COLORS['threshold'], linestyle='--', 
               linewidth=1.5, label=f'Detection Threshold ({threshold:.1f} GB/s)')
    
    # 基线参考线
    baseline = results['baseline_gbps']
    ax.axhline(baseline, color='gray', linestyle=':', 
               linewidth=1.0, alpha=0.5, label=f'Baseline ({baseline:.1f} GB/s)')
    
    # 标注故障注入时段
    ax.text(fault1_start_min + 2.5, 22, 'Fault 1', 
            fontsize=7, ha='left', color=COLORS['fault'])
    ax.text(fault2_start_min + 2.5, 22, 'Fault 2', 
            fontsize=7, ha='left', color=COLORS['fault'])
    
    # 坐标轴设置
    ax.set_xlabel('Time (minutes)', fontsize=9)
    ax.set_ylabel('Bandwidth (GB/s)', fontsize=9)
    ax.set_ylim(0, 25)
    ax.legend(loc='upper right', frameon=False, fontsize=7)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.3, linewidth=0.5)
    
    plt.tight_layout()
    
    # 保存
    for fmt in ['pdf', 'png']:
        fig.savefig(OUTPUT_DIR / f'p0.4_bandwidth_timeseries.{fmt}', dpi=300)
    print(f"✓ Figure 1 saved: {OUTPUT_DIR / 'p0.4_bandwidth_timeseries.pdf'}")
    plt.close()


def plot_metrics_comparison():
    """
    Figure 2: 召回率和精确率对比
    对比两次注入的检测效果
    """
    # 手动计算第1次注入的指标（从第一次分析结果）
    # 第1次：召回率 52.10%, 精确率 51.23%
    # 第2次：召回率 49.20%, 精确率 47.48%
    metrics = {
        'Fault 1\n(1ms BOTH)': {'recall': 52.10, 'precision': 51.23},
        'Fault 2\n(1ms BOTH)': {'recall': 49.20, 'precision': 47.48},
    }
    
    labels = list(metrics.keys())
    recall = [metrics[k]['recall'] for k in labels]
    precision = [metrics[k]['precision'] for k in labels]
    
    x = np.arange(len(labels))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(4, 3))
    
    # 绘制柱状图
    bars1 = ax.bar(x - width/2, recall, width, label='Recall', 
                   color=COLORS['baseline'], edgecolor='black', linewidth=0.8)
    bars2 = ax.bar(x + width/2, precision, width, label='Precision', 
                   color=COLORS['recovery'], edgecolor='black', linewidth=0.8)
    
    # 添加目标线（80% 召回率）
    ax.axhline(80, color=COLORS['threshold'], linestyle='--', 
               linewidth=1.5, alpha=0.7, label='Target (80%)')
    
    # 在柱子上标注数值
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 1.5,
                    f'{height:.1f}%', ha='center', va='bottom', fontsize=7)
    
    # 坐标轴设置
    ax.set_ylabel('Percentage (%)', fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylim(0, 100)
    ax.legend(loc='upper right', frameon=False, fontsize=7)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, axis='y', alpha=0.3, linewidth=0.5)
    
    plt.tight_layout()
    
    # 保存
    for fmt in ['pdf', 'png']:
        fig.savefig(OUTPUT_DIR / f'p0.4_metrics_comparison.{fmt}', dpi=300)
    print(f"✓ Figure 2 saved: {OUTPUT_DIR / 'p0.4_metrics_comparison.pdf'}")
    plt.close()


def plot_detection_latency():
    """
    Figure 3: 检测延迟条形图
    验证是否满足 < 10 秒目标
    """
    # 检测延迟数据
    latencies = {
        'Fault 1\n(1ms BOTH)': 11.23,
        'Fault 2\n(1ms BOTH)': 14.65,
    }
    
    labels = list(latencies.keys())
    values = list(latencies.values())
    
    fig, ax = plt.subplots(figsize=(4, 3))
    
    # 绘制条形图（横向）
    bars = ax.barh(labels, values, color=COLORS['baseline'], 
                   edgecolor='black', linewidth=0.8)
    
    # 目标线（10 秒）
    ax.axvline(10, color=COLORS['threshold'], linestyle='--', 
               linewidth=1.5, alpha=0.7, label='Target (<10s)')
    
    # 标注数值
    for i, (bar, val) in enumerate(zip(bars, values)):
        ax.text(val + 0.5, i, f'{val:.2f}s', 
                va='center', fontsize=7, color='black')
    
    # 坐标轴设置
    ax.set_xlabel('Detection Latency (seconds)', fontsize=9)
    ax.set_xlim(0, 18)
    ax.legend(loc='lower right', frameon=False, fontsize=7)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, axis='x', alpha=0.3, linewidth=0.5)
    
    plt.tight_layout()
    
    # 保存
    for fmt in ['pdf', 'png']:
        fig.savefig(OUTPUT_DIR / f'p0.4_detection_latency.{fmt}', dpi=300)
    print(f"✓ Figure 3 saved: {OUTPUT_DIR / 'p0.4_detection_latency.pdf'}")
    plt.close()


def main():
    print("=" * 60)
    print("生成 P0.4 实验发表级图表")
    print("=" * 60)
    
    # 加载数据
    print("\n加载数据...")
    ts_df, results = load_data()
    print(f"  时间序列: {len(ts_df)} 条带宽探针记录")
    print(f"  基线: {results['baseline_gbps']:.2f} GB/s")
    print(f"  阈值: {results['degradation_threshold_gbps']:.2f} GB/s")
    
    # 生成图表
    print("\n生成图表...")
    plot_bandwidth_timeseries(ts_df, results)
    plot_metrics_comparison()
    plot_detection_latency()
    
    print("\n" + "=" * 60)
    print("✓ 所有图表已生成")
    print(f"输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
