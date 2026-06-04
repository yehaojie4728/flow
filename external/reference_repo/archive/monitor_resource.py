#!/usr/bin/python3
import time
import argparse
import csv
import os
import signal
import sys

# Global flag to control the loop
running = True

def signal_handler(sig, frame):
    global running
    print("\nStopping monitor...")
    running = False

def get_process_children(pid):
    """Recursively get all child PIDs using /proc filesystem."""
    children = []
    try:
        # Iterate over all processes in /proc
        for p in os.listdir('/proc'):
            if p.isdigit():
                try:
                    with open(f'/proc/{p}/stat', 'r') as f:
                        stat = f.read().split()
                        # PPID is at index 3 (0-based)
                        ppid = stat[3]
                        if ppid == str(pid):
                            children.append(int(p))
                            children.extend(get_process_children(int(p)))
                except (IOError, FileNotFoundError):
                    continue
    except Exception:
        pass
    return children

def get_process_stats(pid):
    """Get CPU and Memory stats for a PID using /proc filesystem."""
    try:
        # Get memory (RSS) from /proc/[pid]/statm
        # statm: size resident share text lib data dt
        # resident is index 1, pages
        with open(f'/proc/{pid}/statm', 'r') as f:
            statm = f.read().split()
            rss_pages = int(statm[1])
            page_size = os.sysconf('SC_PAGE_SIZE')
            rss_bytes = rss_pages * page_size
            
        # Get CPU time from /proc/[pid]/stat
        # utime (13), stime (14), cutime (15), cstime (16)
        with open(f'/proc/{pid}/stat', 'r') as f:
            stat = f.read().split()
            utime = int(stat[13])
            stime = int(stat[14])
            total_time = utime + stime
            
        return rss_bytes, total_time
    except (IOError, FileNotFoundError):
        return 0, 0

def get_system_uptime():
    with open('/proc/uptime', 'r') as f:
        return float(f.read().split()[0])

def monitor_process(pid_name, output_file, interval=1.0):
    global running
    
    # Initialize CSV file
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Timestamp', 'CPU_Percent', 'Memory_MB', 'Memory_Percent'])

    target_pid = None
    
    # Check if input is a PID
    if pid_name.isdigit():
        if os.path.exists(f"/proc/{pid_name}"):
            target_pid = int(pid_name)
            print(f"Monitoring PID {target_pid}")
        else:
            print(f"Error: PID {pid_name} not found.")
            return
    else:
        print(f"Waiting for process '{pid_name}' to start...")
        # Wait for process to appear
        while running:
            found = False
            for p in os.listdir('/proc'):
                if p.isdigit():
                    try:
                        with open(f'/proc/{p}/cmdline', 'r') as f:
                            cmdline = f.read().replace('\0', ' ')
                            if pid_name in cmdline:
                                target_pid = int(p)
                                found = True
                                break
                    except (IOError, FileNotFoundError):
                        continue
            
            if found:
                print(f"Process found: PID {target_pid}")
                break
            
            time.sleep(1)
        
    if not running or not target_pid:
        return

    print(f"Monitoring started. Data saving to {output_file}")
    
    # Get total system memory for percentage calculation
    total_mem = 0
    with open('/proc/meminfo', 'r') as f:
        for line in f:
            if line.startswith('MemTotal:'):
                total_mem = int(line.split()[1]) * 1024 # KB to Bytes
                break
                
    clk_tck = os.sysconf('SC_CLK_TCK')
    
    # Initial stats for CPU calculation
    prev_total_time = 0
    prev_uptime = get_system_uptime()
    
    # First pass to initialize prev values
    current_rss, current_time = get_process_stats(target_pid)
    children = get_process_children(target_pid)
    for child in children:
        c_rss, c_time = get_process_stats(child)
        current_rss += c_rss
        current_time += c_time
    prev_total_time = current_time
    
    time.sleep(interval) # Wait for first interval
    
    # Monitor loop
    with open(output_file, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        while running:
            try:
                # Check if process is still running
                if not os.path.exists(f"/proc/{target_pid}"):
                    print("Process terminated.")
                    break
                
                # Get current stats
                current_uptime = get_system_uptime()
                current_rss, current_time = get_process_stats(target_pid)
                
                # Aggregate children
                children = get_process_children(target_pid)
                for child in children:
                    c_rss, c_time = get_process_stats(child)
                    current_rss += c_rss
                    current_time += c_time
                
                # Calculate CPU usage
                # CPU usage = (delta process time / delta uptime) * 100
                # Note: This is roughly equivalent to "top", possibly > 100% on multi-core
                delta_time = current_time - prev_total_time
                delta_seconds = current_uptime - prev_uptime
                
                cpu_pct = 0.0
                if delta_seconds > 0:
                    cpu_pct = (delta_time / clk_tck) / delta_seconds * 100.0
                
                # Update prev values
                prev_total_time = current_time
                prev_uptime = current_uptime
                
                # Memory stats
                mem_mb = current_rss / 1024 / 1024
                mem_pct = (current_rss / total_mem) * 100
                
                timestamp = time.time()
                writer.writerow([timestamp, cpu_pct, mem_mb, mem_pct])
                csvfile.flush()
                
                time.sleep(interval)
                
            except Exception as e:
                print(f"Error: {e}")
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor CPU and Memory usage of a specific process")
    parser.add_argument("process_name", help="Name or partial command line of the process to monitor")
    parser.add_argument("--output", default="resource_usage.csv", help="Output CSV file path")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds")
    
    args = parser.parse_args()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    monitor_process(args.process_name, args.output, args.interval)
