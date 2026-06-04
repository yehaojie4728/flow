#!/usr/bin/python3
import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os

def plot_resource_usage(csv_file, output_image):
    if not os.path.exists(csv_file):
        print(f"Error: CSV file {csv_file} not found.")
        return

    try:
        df = pd.read_csv(csv_file)
        
        # Optimize for large datasets: Downsample if too many points
        # If we have 2 hours of data at 1s interval, that's ~7200 points.
        # Matplotlib can handle this easily, but for clarity and file size, we can downsample.
        MAX_POINTS = 5000
        if len(df) > MAX_POINTS:
            print(f"Dataset has {len(df)} points. Downsampling to ~{MAX_POINTS} points for plotting.")
            step = len(df) // MAX_POINTS
            # Use rolling mean to smooth out noise before sampling, or just sample
            # Rolling mean is better to show trends
            df_sampled = df.iloc[::step].copy()
        else:
            df_sampled = df

        # Convert timestamp to relative time (seconds from start)
        start_time = df_sampled['Timestamp'].iloc[0]
        df_sampled['Relative_Time'] = df_sampled['Timestamp'] - start_time
        
        # Create figure with two subplots (CPU and Memory)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        
        # Plot CPU Usage
        ax1.plot(df_sampled['Relative_Time'], df_sampled['CPU_Percent'], color='b', label='CPU Usage', linewidth=0.8)
        ax1.set_ylabel('CPU Usage (%)')
        ax1.set_title(f'Resource Usage Over Time (Process + Children)')
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper right')
        
        # Plot Memory Usage
        ax2.plot(df_sampled['Relative_Time'], df_sampled['Memory_MB'], color='r', label='Memory Usage (RSS)', linewidth=0.8)
        ax2.set_ylabel('Memory (MB)')
        ax2.set_xlabel('Time (seconds)')
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper right')
        
        # Add summary stats to the plot
        avg_cpu = df['CPU_Percent'].mean()
        max_cpu = df['CPU_Percent'].max()
        avg_mem = df['Memory_MB'].mean()
        max_mem = df['Memory_MB'].max()
        
        plt.figtext(0.15, 0.95, f"Avg CPU: {avg_cpu:.1f}% | Max CPU: {max_cpu:.1f}%", fontsize=10, bbox={"facecolor":"white", "alpha":0.5, "pad":5})
        plt.figtext(0.55, 0.95, f"Avg Mem: {avg_mem:.1f} MB | Max Mem: {max_mem:.1f} MB", fontsize=10, bbox={"facecolor":"white", "alpha":0.5, "pad":5})
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.95]) # Adjust layout to make room for title/stats
        plt.savefig(output_image, dpi=150)
        print(f"Plot saved to {output_image}")
        
    except Exception as e:
        print(f"Error plotting data: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot resource usage from CSV data")
    parser.add_argument("csv_file", help="Input CSV file path")
    parser.add_argument("--output", default="resource_usage.png", help="Output image file path")
    
    args = parser.parse_args()
    
    plot_resource_usage(args.csv_file, args.output)
