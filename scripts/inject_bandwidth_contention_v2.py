#!/usr/bin/env python3
"""
带宽竞争注入器 v2 — 基于 ProbeExecutor 实现

复用已验证可工作的 ProbeExecutor，循环执行大块 memcpy 占用带宽。

用法:
  # 启动注入（占用约 50% 带宽）
  python inject_bandwidth_contention_v2.py --size-mb 128 --interval-ms 10 --duration 300

  # Ctrl+C 停止

参数:
  --size-mb      每次 memcpy 的数据块大小 (MB, 默认 128)
  --interval-ms  两次 memcpy 之间的间隔 (ms, 默认 10)
  --duration     持续时间 (秒, 0=无限, 默认 300)
  --direction    方向: H2D, D2H, BOTH (默认 D2H，因为训练主要是 D2H)

示例:
  # 轻度拥塞 (约 30% 占用)
  python inject_bandwidth_contention_v2.py --size-mb 64 --interval-ms 20 --duration 180

  # 重度拥塞 (约 70% 占用)
  python inject_bandwidth_contention_v2.py --size-mb 256 --interval-ms 5 --duration 180
"""
import argparse
import sys
import time
from pathlib import Path

# 导入 ProbeExecutor
CODE_DIR = Path(__file__).resolve().parent.parent / "code"
sys.path.insert(0, str(CODE_DIR / "probe_scheduler"))

from probe_executor import ProbeExecutor


class BandwidthContender:
    """带宽竞争注入器，基于 ProbeExecutor。"""

    def __init__(self, device_id=0, size_mb=128, interval_ms=10, direction="D2H"):
        self.device_id = device_id
        self.size_bytes = 128 * 1024 * 1024  # probe_bandwidth 固定 128MB
        self.interval_sec = interval_ms / 1000.0
        self.direction = direction

        # 使用 ProbeExecutor（已验证可工作）
        self.executor = ProbeExecutor(device_id=device_id)
        self.executor.open(max_probe_size=self.size_bytes)

        print(f"✓ ProbeExecutor 初始化成功 (设备 {device_id})")
        print(f"  Buffer 大小: 128 MB (probe_bandwidth 固定)")
        print(f"  间隔: {interval_ms} ms")
        print(f"  方向: {direction}")

        self._running = False
        self._total_copies = 0
        self._total_bytes = 0

    def run(self, duration_sec=0):
        """启动带宽竞争注入。"""
        print("\n" + "=" * 60)
        print("带宽竞争注入器启动 (基于 ProbeExecutor)")
        print("  按 Ctrl+C 停止")
        print("=" * 60)

        self._running = True
        start_time = time.time()

        try:
            while self._running:
                # 使用 probe_bandwidth 或 probe_latency 执行真实 memcpy
                # probe_bandwidth 会执行 128MB 的 memcpy
                # probe_latency 会执行小块 memcpy
                
                if self.direction in ("D2H", "BOTH"):
                    result = self.executor.probe_bandwidth(direction="D2H")
                    if result.success:
                        self._total_copies += 1
                        self._total_bytes += self.size_bytes
                    else:
                        print(f"⚠ D2H probe failed: {result.error_msg}", flush=True)

                if self.direction in ("H2D", "BOTH"):
                    result = self.executor.probe_bandwidth(direction="H2D")
                    if result.success:
                        self._total_copies += 1
                        self._total_bytes += self.size_bytes
                    else:
                        print(f"⚠ H2D probe failed: {result.error_msg}", flush=True)

                # 间隔
                if self.interval_sec > 0:
                    time.sleep(self.interval_sec)

                # 定期输出状态
                elapsed = time.time() - start_time
                if self._total_copies % 50 == 0 and self._total_copies > 0:
                    gb_transferred = self._total_bytes / (1024**3)
                    avg_gbps = gb_transferred / elapsed if elapsed > 0 else 0
                    print(
                        f"  [{elapsed:.1f}s] {self._total_copies} copies, "
                        f"{gb_transferred:.2f} GB, avg {avg_gbps:.2f} GB/s",
                        flush=True,
                    )

                # 检查持续时间
                if duration_sec > 0 and elapsed >= duration_sec:
                    print(f"\n已达到持续时间 {duration_sec} 秒，停止注入")
                    break

        except KeyboardInterrupt:
            print("\n\n收到 Ctrl+C，停止注入...")

        finally:
            self.stop()

    def stop(self):
        """停止注入并释放资源。"""
        self._running = False

        gb_transferred = self._total_bytes / (1024**3)

        print("\n" + "=" * 60)
        print("带宽竞争注入统计")
        print("=" * 60)
        print(f"  总 memcpy 次数: {self._total_copies}")
        print(f"  总传输数据: {gb_transferred:.2f} GB")
        print("=" * 60)

        # 释放资源
        if hasattr(self, "executor") and self.executor:
            self.executor.close()
        print("✓ ProbeExecutor 已关闭")


def main():
    parser = argparse.ArgumentParser(
        description="NPU 带宽竞争注入器 v2 (基于 ProbeExecutor)"
    )
    parser.add_argument("--device", type=int, default=0, help="NPU 设备 ID (0-7)")
    parser.add_argument("--size-mb", type=int, default=128, help="每次 memcpy 数据块大小 (MB)")
    parser.add_argument("--interval-ms", type=int, default=10, help="两次 memcpy 间隔 (ms)")
    parser.add_argument("--duration", type=int, default=300, help="持续时间 (秒), 0=无限")
    parser.add_argument(
        "--direction",
        type=str,
        default="D2H",
        choices=["H2D", "D2H", "BOTH"],
        help="memcpy 方向",
    )
    args = parser.parse_args()

    contender = BandwidthContender(
        device_id=args.device,
        size_mb=args.size_mb,
        interval_ms=args.interval_ms,
        direction=args.direction,
    )
    contender.run(duration_sec=args.duration)


if __name__ == "__main__":
    main()
