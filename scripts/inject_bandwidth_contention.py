#!/usr/bin/env python3
"""
带宽竞争注入器 — 通过持续 memcpy 占用 NPU H2D/D2H 链路

原理:
  在后台循环执行大块 memcpy，造成与训练的带宽竞争，
  使探针测到的带宽下降（真实的链路拥塞，不是软件伪造）

用法:
  # 启动注入（占用约 50% 带宽）
  python inject_bandwidth_contention.py --device 0 --size-mb 128 --interval-ms 10 --duration 300

  # Ctrl+C 停止

参数:
  --device       NPU 设备 ID (0-7)
  --size-mb      每次 memcpy 的数据块大小 (MB)
  --interval-ms  两次 memcpy 之间的间隔 (ms), 0=无间隔
  --duration     持续时间 (秒), 0=无限
  --direction    方向: H2D, D2H, BOTH (默认 BOTH)

示例:
  # 轻度拥塞 (约 30% 占用)
  python inject_bandwidth_contention.py --size-mb 64 --interval-ms 20

  # 重度拥塞 (约 70% 占用)
  python inject_bandwidth_contention.py --size-mb 256 --interval-ms 5

  # 极限拥塞 (接近 100%)
  python inject_bandwidth_contention.py --size-mb 512 --interval-ms 0
"""
import argparse
import sys
import time
from pathlib import Path

# 导入 probe_executor 的 AscendCL 接口
CODE_DIR = Path(__file__).resolve().parent.parent / "code"
sys.path.insert(0, str(CODE_DIR / "probe_scheduler"))

from probe_executor import AscendCL, MemcpyDirection, ACL_SUCCESS


class BandwidthContender:
    """带宽竞争注入器。"""

    def __init__(self, device_id=0, size_mb=128, interval_ms=10, direction="BOTH"):
        self.device_id = device_id
        self.size_bytes = size_mb * 1024 * 1024
        self.interval_sec = interval_ms / 1000.0
        self.direction = direction

        # 初始化 AscendCL
        self.acl = AscendCL()
        ret = self.acl._lib.aclInit(None)
        if ret != ACL_SUCCESS:
            raise RuntimeError(f"aclInit failed: {ret}")

        ret = self.acl._lib.aclrtSetDevice(device_id)
        if ret != ACL_SUCCESS:
            raise RuntimeError(f"aclrtSetDevice({device_id}) failed: {ret}")

        # 分配 host 和 device buffer
        self.host_ptr = self.acl.alloc_host(self.size_bytes)
        self.device_ptr = self.acl.alloc_device(self.size_bytes)

        print(f"✓ AscendCL 初始化成功 (设备 {device_id})")
        print(f"  Buffer 大小: {size_mb} MB")
        print(f"  间隔: {interval_ms} ms")
        print(f"  方向: {direction}")

        self._running = False
        self._total_copies = 0
        self._total_bytes = 0

    def run(self, duration_sec=0):
        """启动带宽竞争注入。

        Args:
            duration_sec: 持续时间(秒), 0=无限运行
        """
        print("\n" + "=" * 60)
        print("带宽竞争注入器启动")
        print("  按 Ctrl+C 停止")
        print("=" * 60)

        self._running = True
        start_time = time.time()

        try:
            while self._running:
                # H2D memcpy
                if self.direction in ("H2D", "BOTH"):
                    ret = self.acl.memcpy(
                        self.device_ptr,
                        self.size_bytes,
                        self.host_ptr,
                        self.size_bytes,
                        MemcpyDirection.H2D,
                    )
                    if ret != ACL_SUCCESS:
                        print(f"⚠ H2D memcpy failed: {ret}", flush=True)
                    else:
                        self._total_copies += 1
                        self._total_bytes += self.size_bytes

                # D2H memcpy
                if self.direction in ("D2H", "BOTH"):
                    ret = self.acl.memcpy(
                        self.host_ptr,
                        self.size_bytes,
                        self.device_ptr,
                        self.size_bytes,
                        MemcpyDirection.D2H,
                    )
                    if ret != ACL_SUCCESS:
                        print(f"⚠ D2H memcpy failed: {ret}", flush=True)
                    else:
                        self._total_copies += 1
                        self._total_bytes += self.size_bytes

                # 间隔
                if self.interval_sec > 0:
                    time.sleep(self.interval_sec)

                # 定期输出状态
                elapsed = time.time() - start_time
                if self._total_copies % 100 == 0:
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
        if hasattr(self, "host_ptr") and self.host_ptr:
            self.acl.free_host(self.host_ptr)
        if hasattr(self, "device_ptr") and self.device_ptr:
            self.acl.free_device(self.device_ptr)

        self.acl._lib.aclrtResetDevice(self.device_id)
        self.acl._lib.aclFinalize()
        print("✓ AscendCL 资源已释放")


def main():
    parser = argparse.ArgumentParser(
        description="NPU 带宽竞争注入器 (真实 memcpy 占用链路)"
    )
    parser.add_argument("--device", type=int, default=0, help="NPU 设备 ID (0-7)")
    parser.add_argument("--size-mb", type=int, default=128, help="每次 memcpy 数据块大小 (MB)")
    parser.add_argument("--interval-ms", type=int, default=10, help="两次 memcpy 间隔 (ms)")
    parser.add_argument("--duration", type=int, default=0, help="持续时间 (秒), 0=无限")
    parser.add_argument(
        "--direction",
        type=str,
        default="BOTH",
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
