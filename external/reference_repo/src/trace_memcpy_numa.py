#!/usr/bin/python3
import argparse
import glob
import os
import signal
import sys
import time

try:
    from bcc import BPF
except ImportError:
    from bpfcc import BPF
# 解析命令行参数
parser = argparse.ArgumentParser(description="Trace aclrtMemcpy with NUMA and NPU topology info.")
parser.add_argument("--min-size", type=int, default=1024*1024, help="Minimum size in bytes to trace (default: 1MB)")
parser.add_argument("--output", type=str, default="aclrtMemcpy_numa_trace.log", help="Output file path (default: aclrtMemcpy_numa_trace.log)")
parser.add_argument("--window-ms", type=int, default=100, help="Aggregation window in ms (default: 100)")
parser.add_argument("--agg-output", type=str, default="", help="Aggregated output file path")
args = parser.parse_args()

min_size = args.min_size
output_file = args.output
window_ms = max(1, args.window_ms)
agg_output_file = args.agg_output if args.agg_output else (output_file + ".agg")

print(f"Tracing aclrtMemcpy (Size >= {min_size} B) with Topology Info...")
print(f"Output will be saved to {output_file}")
print(f"Aggregation: src->dst overlap-merge mode (window-ms={window_ms} kept for compatibility)")
print(f"Aggregated output will be saved to {agg_output_file}")


def _append_candidate(candidates, path):
    if path and path not in candidates:
        candidates.append(path)


def resolve_ascendcl_lib():
    candidates = []
    env_candidates = [
        os.environ.get("ASCEND_CL_LIB"),
        os.environ.get("ASCENDCL_LIB"),
    ]
    for env_path in env_candidates:
        _append_candidate(candidates, env_path)

    toolkit_home = os.environ.get("ASCEND_TOOLKIT_HOME")
    if toolkit_home:
        for rel in (
            "lib64/libascendcl.so",
            "aarch64-linux/lib64/libascendcl.so",
            "arm64-linux/lib64/libascendcl.so",
        ):
            _append_candidate(candidates, os.path.join(toolkit_home, rel))

    for path in (
        "/usr/local/Ascend/cann-8.5.0/aarch64-linux/lib64/libascendcl.so",
        "/usr/local/Ascend/cann-8.5.0/lib64/libascendcl.so",
        "/usr/local/Ascend/cann-8.5.0/arm64-linux/lib64/libascendcl.so",
        "/usr/local/Ascend/ascend-toolkit/latest/lib64/libascendcl.so",
        "/usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/lib64/libascendcl.so",
        "/usr/local/Ascend/ascend-toolkit/latest/arm64-linux/lib64/libascendcl.so",
        "/usr/local/Ascend/cann/lib64/libascendcl.so",
        "/usr/local/Ascend/cann/aarch64-linux/lib64/libascendcl.so",
        "/usr/local/Ascend/cann/arm64-linux/lib64/libascendcl.so",
    ):
        _append_candidate(candidates, path)

    for pattern in (
        "/usr/local/Ascend/**/lib64/libascendcl.so",
        "/usr/local/Ascend/**/aarch64-linux/lib64/libascendcl.so",
        "/usr/local/Ascend/**/arm64-linux/lib64/libascendcl.so",
    ):
        for path in sorted(glob.glob(pattern, recursive=True)):
            if "/devlib/" in path:
                continue
            _append_candidate(candidates, path)

    for path in candidates:
        if os.path.isfile(path):
            return path

    raise FileNotFoundError(
        "未找到 libascendcl.so，请设置 ASCEND_CL_LIB 或 ASCEND_TOOLKIT_HOME。"
    )


def resolve_bpf_cflags():
    target = os.environ.get("BPF_CLANG_TARGET", "aarch64-linux-gnu").strip() or "aarch64-linux-gnu"
    extra = os.environ.get("BPF_CFLAGS", "").strip()
    cflags = ["-target", target]
    if extra:
        cflags.extend(extra.split())
    return cflags

# -----------------------------------------------------------------------------
# 1. 预加载 CPU -> NUMA 映射表
# -----------------------------------------------------------------------------
cpu_to_numa = {}
try:
    if os.path.exists("/sys/devices/system/cpu"):
        for cpu_dir in os.listdir("/sys/devices/system/cpu"):
            if cpu_dir.startswith("cpu") and cpu_dir[3:].isdigit():
                cpu_id = int(cpu_dir[3:])
                # 查找 nodeX 目录
                path = f"/sys/devices/system/cpu/{cpu_dir}"
                for entry in os.listdir(path):
                    if entry.startswith("node") and entry[4:].isdigit():
                        node_id = int(entry[4:])
                        cpu_to_numa[cpu_id] = node_id
                        break
except Exception as e:
    print(f"Warning: Failed to build CPU-NUMA map: {e}")

def get_current_numa_node(pid, tid):
    """
    获取指定线程当前运行在哪颗 CPU 上，从而推断其 NUMA 节点。
    注意：这只是发起 memcpy 的 CPU，并不绝对代表内存所在的 NUMA，
    但在未发生严重页迁移的情况下，通常具有很强的相关性。
    """
    try:
        with open(f"/proc/{pid}/task/{tid}/stat", "r") as f:
            content = f.read()
            # stat 文件的第 39 个字段 (索引 38) 是 processor
            # 格式: pid (comm) state ...
            parts = content.split(")")
            if len(parts) < 2: return "?"
            fields = parts[1].split()
            # split 后 fields[0] 是 state (第 3 个字段)
            # processor 是第 39 个字段，所以索引是 39 - 3 - 1 = 35 ??? 
            # 让我们重新计算：
            # comm 是第 2 个字段，被 () 包裹。
            # fields[0] 是 state (第 3 个字段)
            # ...
            # processor 是第 39 个字段。
            # 所以 offset 是 39 - 3 = 36。 fields[36] 应该是 processor。
            if len(fields) > 36:
                cpu_id = int(fields[36])
                return cpu_to_numa.get(cpu_id, "?")
    except:
        pass
    return "?"

# -----------------------------------------------------------------------------
# 2. BPF 程序
# -----------------------------------------------------------------------------
bpf_text = """
#include <uapi/linux/ptrace.h>

struct start_t {
    u64 ts;
    u64 dst;
    u64 destMax;
    u64 src;
    u64 count;
    u64 kind;
};

struct data_t {
    u64 pid;
    u64 tid;
    u64 ts;
    u64 dst;
    u64 destMax;
    u64 src;
    u64 count;
    u64 kind;
    u64 delta;
    s32 current_device; // 记录线程当前的 Device Context
};

// 记录每个线程当前设置的 Device ID
BPF_HASH(thread_device, u32, s32);

// 记录 Memcpy 开始信息
BPF_HASH(start_map, u64, struct start_t);

BPF_PERF_OUTPUT(events);

// Hook aclrtSetDevice 以捕获当前线程的 Device Context
int trace_set_device(struct pt_regs *ctx) {
    u32 tid = bpf_get_current_pid_tgid();
    s32 dev_id = (s32)PT_REGS_PARM1(ctx);
    thread_device.update(&tid, &dev_id);
    
    return 0;
}

// Hook aclrtMemcpy
int probe_entry(struct pt_regs *ctx) {
    u64 count = PT_REGS_PARM4(ctx);
    if (count < %d) return 0;

    u64 pid_tgid = bpf_get_current_pid_tgid();
    struct start_t val = {};
    val.ts = bpf_ktime_get_ns();
    val.dst = PT_REGS_PARM1(ctx);
    val.destMax = PT_REGS_PARM2(ctx);
    val.src = PT_REGS_PARM3(ctx);
    val.count = count;
    val.kind = PT_REGS_PARM5(ctx);

    start_map.update(&pid_tgid, &val);
    return 0;
}

int probe_return(struct pt_regs *ctx) {
    u64 pid_tgid = bpf_get_current_pid_tgid();
    u32 tid = (u32)pid_tgid;
    struct start_t *val = start_map.lookup(&pid_tgid);

    if (val != 0) {
        u64 delta = bpf_ktime_get_ns() - val->ts;
        struct data_t data = {};
        
        data.pid = pid_tgid >> 32;
        data.tid = tid;
        data.ts = val->ts;
        data.dst = val->dst;
        data.destMax = val->destMax;
        data.src = val->src;
        data.count = val->count;
        data.kind = val->kind;
        data.delta = delta;
        
        // 获取当前线程的 Device ID
        s32 *dev_ptr = thread_device.lookup(&tid);
        data.current_device = (dev_ptr) ? *dev_ptr : -1; // -1 表示未知
        
        events.perf_submit(ctx, &data, sizeof(data));
        start_map.delete(&pid_tgid);
    }
    return 0;
}
""" % min_size

# Load BPF program
bpf_cflags = resolve_bpf_cflags()
print(f"Using BPF cflags: {' '.join(bpf_cflags)}")
b = BPF(text=bpf_text, cflags=bpf_cflags)

# Attach probes
lib_path = resolve_ascendcl_lib()
print(f"Using AscendCL library: {lib_path}")
b.attach_uprobe(name=lib_path, sym="aclrtSetDevice", fn_name="trace_set_device")
b.attach_uprobe(name=lib_path, sym="aclrtMemcpy", fn_name="probe_entry")
b.attach_uretprobe(name=lib_path, sym="aclrtMemcpy", fn_name="probe_return")

# Open output file
f = open(output_file, "w")
agg_f = open(agg_output_file, "w")
# Write Header to file
f.write(
    "PID,TID,Source,Destination,Size_MB,Latency_us,Bandwidth_GBps,"
    "Start_ns,End_ns,WallStart_ns,WallEnd_ns\n"
)
f.flush()
agg_f.write(
    "WindowStart_ns,WindowEnd_ns,Source,Destination,Bytes_MB,Bandwidth_GBps,"
    "WindowStartWall_ns,WindowEndWall_ns,Duration_ms,Packet_Count\n"
)
agg_f.flush()

header_str = f"{'Source':>20} -> {'Destination':<20} | {'Size':>10} | {'Latency':>10} | {'BW':>10}"
print(header_str)
print("-" * 90)

active_windows = {}


def flush_merged_window(key, state):
    duration_ns = max(1, int(state["end_ns"] - state["start_ns"]))
    bytes_sum = float(state["bytes_sum"])
    bw_gbps = bytes_sum / duration_ns
    bytes_mb = bytes_sum / (1024 * 1024)
    duration_ms = duration_ns / 1e6
    src_str, dst_str = key
    print(
        f"[AGG] {src_str} -> {dst_str} | window=[{state['start_ns']},{state['end_ns']}) "
        f"| {bytes_mb:>8.2f} MB | {bw_gbps:>7.2f} GB/s | packets={state['packet_count']}"
    )
    agg_f.write(
        f"{int(state['start_ns'])},{int(state['end_ns'])},{src_str},{dst_str},"
        f"{bytes_mb:.2f},{bw_gbps:.2f},{int(state['wall_start_ns'])},{int(state['wall_end_ns'])},"
        f"{duration_ms:.3f},{int(state['packet_count'])}\n"
    )
    agg_f.flush()


def merge_or_flush_window(src_str, dst_str, start_ns, end_ns, wall_start_ns, wall_end_ns, count_bytes):
    key = (src_str, dst_str)
    state = active_windows.get(key)
    if state is None:
        active_windows[key] = {
            "start_ns": start_ns,
            "end_ns": end_ns,
            "wall_start_ns": wall_start_ns,
            "wall_end_ns": wall_end_ns,
            "bytes_sum": float(count_bytes),
            "packet_count": 1,
        }
        return

    if start_ns <= state["end_ns"]:
        state["start_ns"] = min(state["start_ns"], start_ns)
        state["end_ns"] = max(state["end_ns"], end_ns)
        state["wall_start_ns"] = min(state["wall_start_ns"], wall_start_ns)
        state["wall_end_ns"] = max(state["wall_end_ns"], wall_end_ns)
        state["bytes_sum"] += float(count_bytes)
        state["packet_count"] += 1
        return

    flush_merged_window(key, state)
    active_windows[key] = {
        "start_ns": start_ns,
        "end_ns": end_ns,
        "wall_start_ns": wall_start_ns,
        "wall_end_ns": wall_end_ns,
        "bytes_sum": float(count_bytes),
        "packet_count": 1,
    }

# Callback function
def print_event(cpu, data, size):
    event = b["events"].event(data)
    
    # 1. 获取 NUMA 节点 (Host 侧)
    # 注意：我们只能获取发起调用的 CPU 所在的 NUMA。
    # 对于 H2D，源通常在 Host NUMA；对于 D2H，目的通常在 Host NUMA。
    host_numa = get_current_numa_node(event.pid, event.tid)
    host_desc = f"Host(NUMA {host_numa})"
    
    # 2. 获取 Device ID (NPU 侧)
    # 我们使用 hook 到的 thread_device。
    # 注意：aclrtMemcpy 并不显式带 deviceId 参数，它依赖于当前 context。
    dev_desc = "Device ?"
    if event.current_device >= 0:
        dev_desc = f"NPU {event.current_device}"
    
    # 3. 根据 Kind 推断流向
    # aclrtMemcpyKind:
    # 0: ACL_MEMCPY_HOST_TO_HOST
    # 1: ACL_MEMCPY_HOST_TO_DEVICE
    # 2: ACL_MEMCPY_DEVICE_TO_HOST
    # 3: ACL_MEMCPY_DEVICE_TO_DEVICE
    
    src_str = "?"
    dst_str = "?"
    
    if event.kind == 0: # H2H
        src_str = host_desc
        dst_str = host_desc
    elif event.kind == 1: # H2D
        src_str = host_desc
        dst_str = dev_desc
    elif event.kind == 2: # D2H
        src_str = dev_desc
        dst_str = host_desc
    elif event.kind == 3: # D2D
        src_str = dev_desc
        dst_str = dev_desc
    else:
        src_str = "Unknown"
        dst_str = "Unknown"

    # 计算指标
    latency_us = event.delta / 1000.0
    bw_gbps = 0
    if latency_us > 0:
        bw_gbps = (event.count / 1e9) / (latency_us / 1e6)
    size_mb = event.count / 1024 / 1024
    start_ns = int(event.ts)
    end_ns = int(event.ts + event.delta)
    wall_end_ns = time.time_ns()
    wall_start_ns = wall_end_ns - max(1, int(event.delta))

    # Print to terminal
    print(f"{src_str:>20} -> {dst_str:<20} | {size_mb:>7.2f} MB | {latency_us:>7.2f} us | {bw_gbps:>6.2f} GB/s")
    
    # Write to file (CSV format)
    log_line = (
        f"{event.pid},{event.tid},{src_str},{dst_str},{size_mb:.2f},{latency_us:.2f},{bw_gbps:.2f},"
        f"{start_ns},{end_ns},{wall_start_ns},{wall_end_ns}"
    )
    f.write(log_line + "\n")
    f.flush()
    merge_or_flush_window(
        src_str,
        dst_str,
        start_ns,
        end_ns,
        wall_start_ns,
        wall_end_ns,
        float(event.count),
    )

# Open perf buffer
b["events"].open_perf_buffer(print_event)

def signal_handler(sig, frame):
    for key in sorted(active_windows.keys()):
        flush_merged_window(key, active_windows[key])
    active_windows.clear()
    print("\nReceived signal, detaching...")
    f.close()
    agg_f.close()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

print("Monitoring started. Press Ctrl+C to stop.")
while True:
    try:
        b.perf_buffer_poll()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
