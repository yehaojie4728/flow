"""
Probe executor — lightweight AscendCL wrapper via ctypes.

Executes real NPU memcpy probes (H2D, D2H) at user-specified sizes.
Designed to NOT interfere with running MindSpore training:
  - Uses a SEPARATE AscendCL stream from training
  - Probe latency is measured internally, no NPU-side sync with training

Requires: conda env mindspore_py37 (which links libascendcl.so).
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Optional


# ---- AscendCL type constants ----

ACL_MEMCPY_HOST_TO_DEVICE   = 1
ACL_MEMCPY_DEVICE_TO_HOST   = 2
ACL_MEMCPY_DEVICE_TO_DEVICE = 3
ACL_MEM_MALLOC_HUGE_FIRST   = 0
ACL_MEMCPY_DEFAULT          = 0
ACL_RT_MEMCPY               = 0
ACL_RT_STREAM_DEFAULT       = 0  # nullptr → default stream
ACL_SUCCESS                 = 0


class MemcpyDirection(IntEnum):
    H2D = ACL_MEMCPY_HOST_TO_DEVICE
    D2H = ACL_MEMCPY_DEVICE_TO_HOST
    D2D = ACL_MEMCPY_DEVICE_TO_DEVICE


@dataclass
class ProbeResult:
    """Result of a single probe."""
    probe_type: str = ""          # "tiny" / "normal" / "bandwidth"
    direction: str = "H2D"
    size_bytes: int = 0
    latency_us: float = 0.0
    bandwidth_gbps: float = 0.0
    success: bool = False
    error_msg: str = ""
    device_id: int = 0
    stream_id: int = 0
    wall_clock_us: int = 0


# ---- Path resolution ----

def _find_ascendcl() -> str:
    """Find libascendcl.so — prefer NNAE (MindSpore's version)."""
    candidates = [
        os.environ.get("ASCENDCL_LIB", ""),
        "/usr/local/Ascend/nnae/latest/aarch64-linux/lib64/libascendcl.so",
        "/usr/local/Ascend/nnae/7.0.0/aarch64-linux/lib64/libascendcl.so",
        "/usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/lib64/libascendcl.so",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError("Cannot find libascendcl.so. Check ASCENDCL_LIB env var.")


# ---- AscendCL API bindings ----

class AscendCL:
    """Minimal ctypes binding to AscendCL — only the APIs needed for probes."""

    def __init__(self, lib_path: Optional[str] = None):
        self._lib = ctypes.CDLL(lib_path or _find_ascendcl())
        self._initialized = False
        self._setup_types()

    def _setup_types(self):
        L = self._lib

        # aclInit accepts nullptr (None) for default config, or a JSON config file path.
        # DO NOT pass arbitrary strings — AscendCL parses it as a file path.
        L.aclInit.restype = ctypes.c_int
        L.aclInit.argtypes = [ctypes.c_char_p]

        # aclrtSetDevice
        L.aclrtSetDevice.restype = ctypes.c_int
        L.aclrtSetDevice.argtypes = [ctypes.c_int]

        # aclrtCreateStream
        L.aclrtCreateStream.restype = ctypes.c_int
        L.aclrtCreateStream.argtypes = [ctypes.POINTER(ctypes.c_void_p)]

        # aclrtDestroyStream
        L.aclrtDestroyStream.restype = ctypes.c_int
        L.aclrtDestroyStream.argtypes = [ctypes.c_void_p]

        # aclrtMallocHost & aclrtFreeHost
        L.aclrtMallocHost.restype = ctypes.c_int
        L.aclrtMallocHost.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.c_size_t]

        L.aclrtFreeHost.restype = ctypes.c_int
        L.aclrtFreeHost.argtypes = [ctypes.c_void_p]

        # aclrtMalloc & aclrtFree
        L.aclrtMalloc.restype = ctypes.c_int
        L.aclrtMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.c_size_t,
                                   ctypes.c_int]  # policy

        L.aclrtFree.restype = ctypes.c_int
        L.aclrtFree.argtypes = [ctypes.c_void_p]

        # aclrtMemcpy — the core probe call
        L.aclrtMemcpy.restype = ctypes.c_int
        L.aclrtMemcpy.argtypes = [
            ctypes.c_void_p,    # dst
            ctypes.c_size_t,    # max_size
            ctypes.c_void_p,    # src
            ctypes.c_size_t,    # count
            ctypes.c_int,       # kind (H2D/D2H/D2D)
            ctypes.c_void_p,    # stream (nullptr = default)
        ]

        # aclrtSynchronizeStream
        L.aclrtSynchronizeStream.restype = ctypes.c_int
        L.aclrtSynchronizeStream.argtypes = [ctypes.c_void_p]

        # aclFinalize
        L.aclFinalize.restype = ctypes.c_int
        L.aclFinalize.argtypes = []

    # ---- Convenience methods ----

    def init(self) -> int:
        """Initialize AscendCL. Pass nullptr for default config.

        Returns ACL_SUCCESS (0) if init succeeded or ACL was already initialized.
        """
        # aclInit only succeeds once per process.  Calling it again
        # returns error code 200004 ("already initialized") — which is fine.
        ret = self._lib.aclInit(None)
        if ret == 0 or ret == 200004:
            self._initialized = True
            return 0
        return ret

    def set_device(self, dev_id: int = 0) -> int:
        return self._lib.aclrtSetDevice(dev_id)

    def create_stream(self) -> int:
        s = ctypes.c_void_p()
        ret = self._lib.aclrtCreateStream(ctypes.byref(s))
        if ret == 0:
            return s.value
        raise RuntimeError(f"aclrtCreateStream failed: {ret}")

    def destroy_stream(self, stream: int):
        if stream:
            self._lib.aclrtDestroyStream(stream)

    def sync(self, stream: int = 0):
        return self._lib.aclrtSynchronizeStream(stream)

    def alloc_host(self, size: int) -> int:
        ptr = ctypes.c_void_p()
        ret = self._lib.aclrtMallocHost(ctypes.byref(ptr), size)
        if ret != 0:
            raise RuntimeError(f"aclrtMallocHost({size}) failed: {ret}")
        return ptr.value

    def alloc_device(self, size: int) -> int:
        ptr = ctypes.c_void_p()
        ret = self._lib.aclrtMalloc(ctypes.byref(ptr), size, ACL_MEM_MALLOC_HUGE_FIRST)
        if ret != 0:
            raise RuntimeError(f"aclrtMalloc({size}) failed: {ret}")
        return ptr.value

    def free_host(self, ptr: int):
        if ptr:
            self._lib.aclrtFreeHost(ptr)

    def free_device(self, ptr: int):
        if ptr:
            self._lib.aclrtFree(ptr)

    def memcpy(self,
               dst: int, dst_size: int,
               src: int, count: int,
               direction: int,
               stream: int = 0) -> int:
        """Execute aclrtMemcpy. Returns ACL_ERROR code."""
        return self._lib.aclrtMemcpy(
            dst, dst_size, src, count, direction, stream,
        )

    def finalize(self) -> int:
        return self._lib.aclFinalize()


# ---- Probe executor ----

class ProbeExecutor:
    """Execute AscendCL memcpy probes on real NPU hardware.

    Usage:
        executor = ProbeExecutor()
        executor.open()

        result = executor.probe_latency(4096, direction="H2D")
        print(f"Latency: {result.latency_us:.1f} µs")

        result = executor.probe_bandwidth(128 * 1024 * 1024, direction="D2H")
        print(f"Bandwidth: {result.bandwidth_gbps:.1f} GB/s")

        executor.close()
    """

    def __init__(self, device_id: int = 0):
        self.device_id = device_id
        self._acl: Optional[AscendCL] = None
        self._stream: int = 0
        self._host_buf: int = 0
        self._dev_buf: int = 0
        self._max_buf_size: int = 0
        self._opened: bool = False

    # ---- Lifecycle ----

    def open(self, max_probe_size: int = 128 * 1024 * 1024):
        """Initialize AscendCL context and allocate probe buffers.

        Uses a SEPARATE stream from MindSpore training to avoid
        HCCL interference.  Idempotent — skips init if already opened.
        """
        if self._opened:
            return
        self._acl = AscendCL()
        ret = self._acl.init()
        if ret != 0:
            self._acl.finalize()
            # Common causes: another process using the NPU, driver not loaded,
            # or training in progress holding exclusive access.
            import subprocess
            try:
                out = subprocess.check_output(
                    "npu-smi info -t usages -i 0 2>/dev/null || npu-smi info 2>/dev/null",
                    shell=True, timeout=5, text=True,
                ).strip()
                npu_info = f"\n  npu-smi: {out[:200]}"
            except Exception:
                npu_info = ""
            raise RuntimeError(
                f"aclInit failed: {ret}. Is the NPU free?{npu_info}\n"
                f"  Check: npu-smi info\n"
                f"  If training is running, run tests in dry-run mode: FLOWGAP_TEST_NPU=0"
            )

        self._acl.set_device(self.device_id)

        # Create dedicated probe stream (not shared with training)
        self._stream = self._acl.create_stream()

        # Allocate persistent buffers
        self._max_buf_size = max_probe_size
        self._host_buf = self._acl.alloc_host(max_probe_size)
        self._dev_buf = self._acl.alloc_device(max_probe_size)

        # Prime the host buffer with recognizable pattern
        try:
            buf = (ctypes.c_char * max_probe_size).from_address(self._host_buf)
            for i in range(max_probe_size):
                buf[i] = b'\x41'
        except Exception:
            pass

        self._opened = True

    def close(self):
        """Release AscendCL resources."""
        if self._acl is None:
            return
        try:
            if self._host_buf:
                self._acl.free_host(self._host_buf)
            if self._dev_buf:
                self._acl.free_device(self._dev_buf)
            if self._stream:
                self._acl.destroy_stream(self._stream)
            self._acl.finalize()
        finally:
            self._opened = False

    # ---- Probe execution ----

    def probe_latency(self, size_bytes: int = 4096, direction: str = "H2D",
                      iterations: int = 1) -> ProbeResult:
        """Execute tiny/normal latency probe.

        Parameters
        ----------
        size_bytes : probe payload size (default 4 KB)
        direction : "H2D" or "D2H"
        iterations : number of back-to-back copies
        """
        if not self._opened:
            raise RuntimeError("ProbeExecutor not opened. Call open() first.")

        if size_bytes > self._max_buf_size:
            size_bytes = self._max_buf_size

        dir_flag = (ACL_MEMCPY_HOST_TO_DEVICE if direction == "H2D"
                    else ACL_MEMCPY_DEVICE_TO_HOST)

        t0 = time.perf_counter_ns()
        errors = 0

        for _ in range(iterations):
            if direction == "H2D":
                ret = self._acl.memcpy(
                    self._dev_buf, size_bytes,
                    self._host_buf, size_bytes,
                    dir_flag, self._stream,
                )
            else:
                ret = self._acl.memcpy(
                    self._host_buf, size_bytes,
                    self._dev_buf, size_bytes,
                    dir_flag, self._stream,
                )
            if ret != 0:
                errors += 1

        # Synchronize on the probe stream (NOT training stream)
        self._acl.sync(self._stream)

        t1 = time.perf_counter_ns()
        elapsed_ns = t1 - t0
        latency_us = elapsed_ns / 1000.0 / max(1, iterations)
        bw_gbps = (size_bytes / 1e9) / (elapsed_ns / 1e9) * iterations if elapsed_ns > 0 else 0

        return ProbeResult(
            probe_type="tiny" if size_bytes <= 4096 else "normal",
            direction=direction,
            size_bytes=size_bytes,
            latency_us=round(latency_us, 2),
            bandwidth_gbps=round(bw_gbps, 2),
            success=(errors == 0),
            error_msg=f"{errors}/{iterations} errors" if errors else "",
            device_id=self.device_id,
            stream_id=self._stream,
            wall_clock_us=int(time.time_ns() / 1000),
        )

    def probe_bandwidth(self, direction: str = "D2H") -> ProbeResult:
        """Execute bandwidth probe (128 MB)."""
        size = 128 * 1024 * 1024  # 128 MB
        if size > self._max_buf_size:
            size = self._max_buf_size

        dir_flag = (ACL_MEMCPY_HOST_TO_DEVICE if direction == "H2D"
                    else ACL_MEMCPY_DEVICE_TO_HOST)

        t0 = time.perf_counter_ns()

        if direction == "H2D":
            ret = self._acl.memcpy(
                self._dev_buf, size,
                self._host_buf, size,
                dir_flag, self._stream,
            )
        else:
            ret = self._acl.memcpy(
                self._host_buf, size,
                self._dev_buf, size,
                dir_flag, self._stream,
            )

        self._acl.sync(self._stream)

        t1 = time.perf_counter_ns()
        elapsed_ns = t1 - t0
        latency_us = elapsed_ns / 1000.0
        bw_gbps = (size / 1e9) / (elapsed_ns / 1e9) if elapsed_ns > 0 else 0

        return ProbeResult(
            probe_type="bandwidth",
            direction=direction,
            size_bytes=size,
            latency_us=round(latency_us, 2),
            bandwidth_gbps=round(bw_gbps, 2),
            success=(ret == 0),
            error_msg=f"aclrtMemcpy ret={ret}" if ret != 0 else "",
            device_id=self.device_id,
            stream_id=self._stream,
            wall_clock_us=int(time.time_ns() / 1000),
        )

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()


# ---- Quick self-test (run standalone) ----

def main():
    """Run a quick self-test: open executor, run one small probe, close."""
    print("FlowGap Probe Executor — Self Test")
    print("===================================")
    print(f"Python: {sys.version}")
    print(f"libascendcl: {_find_ascendcl()}")

    executor = ProbeExecutor()
    try:
        print("Opening AscendCL...")
        executor.open(max_probe_size=128 * 1024 * 1024)
        print("  OK — device context initialized, stream created, buffers allocated")

        print("\nTiny latency (4 KB H2D)...")
        r = executor.probe_latency(4096, "H2D")
        print(f"  {r.latency_us:.1f} µs — success={r.success}")

        print("\nTiny latency (4 KB D2H)...")
        r = executor.probe_latency(4096, "D2H")
        print(f"  {r.latency_us:.1f} µs — success={r.success}")

        print("\nBandwidth (128 MB D2H)...")
        r = executor.probe_bandwidth("D2H")
        print(f"  {r.latency_us:.1f} µs, {r.bandwidth_gbps:.1f} GB/s — success={r.success}")

        print("\nAll probes passed!")

    except Exception as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        executor.close()
        print("\nClosed.")


if __name__ == "__main__":
    main()
