"""
FlowEvent Trace Schema — data structures and constants.

Compatible with HostDiagV2 raw CSV format (11-column legacy),
and FlowGap extended format (21-column with direction, async_flag, etc.).

Reference: docs/trace_schema.md
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Tuple
import enum

# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

FLOWEVENT_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Constants — device / NUMA sentinels
# ---------------------------------------------------------------------------

HOST_DEVICE_ID = 0xFFFFFFFF
UNKNOWN_NUMA = 0xFF
UNKNOWN_DEVICE = 0xFFFFFFFE


# ---------------------------------------------------------------------------
# Direction enum
# ---------------------------------------------------------------------------

class Direction(enum.IntEnum):
    H2H = 0
    H2D = 1
    D2H = 2
    D2D = 3

    @classmethod
    def from_kind(cls, kind: int) -> "Direction":
        """Map AscendCL aclrtMemcpyKind to Direction."""
        _map = {0: cls.H2H, 1: cls.H2D, 2: cls.D2H, 3: cls.D2D}
        return _map.get(kind, cls.H2D)  # default H2D for safety

    @classmethod
    def from_string(cls, s: str) -> "Direction":
        """Parse 'H2D', 'D2H', 'D2D', 'H2H'."""
        s = s.strip().upper()
        for d in cls:
            if d.name == s:
                return d
        raise ValueError(f"Unknown direction: {s}")


DIR_LABEL = {
    Direction.H2H: "H2H",
    Direction.H2D: "H2D",
    Direction.D2H: "D2H",
    Direction.D2D: "D2D",
}


# ---------------------------------------------------------------------------
# API type enum
# ---------------------------------------------------------------------------

class ApiType(enum.IntEnum):
    MEMCPY = 0
    MEMCPY_ASYNC = 1
    MEMCPY_2D = 2
    MEMCPY_2D_ASYNC = 3
    STREAM_SYNC = 4
    SET_DEVICE = 5
    MALLOC_HOST = 6
    MALLOC_DEVICE = 7
    FREE_HOST = 8
    FREE_DEVICE = 9


# ---------------------------------------------------------------------------
# Quality flags (bit field)
# ---------------------------------------------------------------------------

class QualityFlag(enum.IntFlag):
    NONE = 0
    UNKNOWN_PATH = 1 << 0
    UNKNOWN_DEVICE = 1 << 1
    ASYNC_UNCERTAINTY = 1 << 2
    TIMESTAMP_JITTER = 1 << 3
    ADDRESS_UNMAPPED = 1 << 4
    RING_DROP = 1 << 5
    MERGED_GAP = 1 << 6
    SYNTHETIC = 1 << 7


# ---------------------------------------------------------------------------
# Probe type codes
# ---------------------------------------------------------------------------

class ProbeType(enum.IntEnum):
    NONE = 0
    TINY_LATENCY = 1
    NORMAL_LATENCY = 2
    BANDWIDTH = 3
    CONFIRMATION = 4


# ---------------------------------------------------------------------------
# Reason codes (why a window is/is not safe)
# ---------------------------------------------------------------------------

class ReasonCode(enum.IntEnum):
    SAFE = 0
    LOW_CONFIDENCE = 1
    GAP_TOO_SHORT = 2
    NO_DATA = 3
    DRIFT_DETECTED = 4
    LOW_DATA_QUALITY = 5
    COOLDOWN = 6


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FlowEvent:
    """Single memcpy / sync event, normalized from raw trace."""
    # Timestamps (monotonic ns)
    ts_enter_ns: int = 0
    ts_exit_ns: int = 0
    ts_submit_ns: int = 0       # for async: user-space est; sync: == ts_enter_ns
    ts_end_est_ns: int = 0      # for async: est completion; sync: == ts_exit_ns
    ts_wall_ns: int = 0         # wall clock at emission

    # Identity
    pid: int = 0
    tid: int = 0
    stream_id: int = 0          # 0 for sync calls

    # Topology
    src_dev: int = 0
    dst_dev: int = 0
    src_numa: int = 0
    dst_numa: int = 0

    # Payload
    size: int = 0               # bytes
    direction: int = Direction.H2D
    async_flag: int = 0         # 0=sync, 1=async
    api_type: int = ApiType.MEMCPY

    # Derived (set by normalizer, default 0 in raw)
    path_id: int = 0
    link_bitmap: int = 0

    quality_flags: int = QualityFlag.NONE

    # ---- computed properties ----
    @property
    def latency_us(self) -> float:
        return (self.ts_exit_ns - self.ts_enter_ns) / 1000.0

    @property
    def size_mb(self) -> float:
        return self.size / (1024.0 * 1024.0)

    @property
    def bw_gbps(self) -> float:
        lat = self.latency_us
        if lat > 0:
            return (self.size / 1e9) / (lat / 1e6)
        return 0.0

    @property
    def is_async(self) -> bool:
        return self.async_flag == 1

    @property
    def is_synthetic(self) -> bool:
        return bool(self.quality_flags & QualityFlag.SYNTHETIC)

    @property
    def direction_label(self) -> str:
        return DIR_LABEL.get(Direction(self.direction), "?")


@dataclass
class BusyInterval:
    """A time interval where a path/link is busy with memcpy traffic."""
    start_ns: int               # monotonic ns
    end_ns: int
    path_id: int = 0
    link_bitmap: int = 0
    bytes_total: int = 0
    event_count: int = 1
    merged: bool = False        # True if this interval merged multiple events

    @property
    def duration_ns(self) -> int:
        return max(0, self.end_ns - self.start_ns)

    @property
    def bandwidth_gbps(self) -> float:
        dur = self.duration_ns / 1e9
        if dur > 0:
            return (self.bytes_total / 1e9) / dur
        return 0.0

    @property
    def size_mb(self) -> float:
        return self.bytes_total / (1024.0 * 1024.0)


@dataclass
class Gap:
    """An idle period between two busy intervals on the same path/link."""
    start_ns: int
    end_ns: int
    path_id: int
    link_bitmap: int = 0

    @property
    def duration_ns(self) -> int:
        return max(0, self.end_ns - self.start_ns)

    def is_safe_for_probe(self, probe_duration_ns: int, safety_margin_ns: int) -> bool:
        return self.duration_ns >= probe_duration_ns + safety_margin_ns


@dataclass
class PathTimeline:
    """Full busy-idle timeline for a single path."""
    path_id: int
    link_bitmap: int = 0
    busy_intervals: List[BusyInterval] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)

    @property
    def num_busy(self) -> int:
        return len(self.busy_intervals)

    @property
    def num_gaps(self) -> int:
        return len(self.gaps)


@dataclass
class ProbeEvent:
    """A probe that was executed on a path."""
    probe_id: int
    path_id: int
    probe_type: int              # ProbeType
    probe_size: int              # bytes
    start_ns: int
    end_ns: int
    latency_us: float = 0.0
    bw_gbps: float = 0.0
    overlap_flag: bool = False   # True if probe overlapped with business traffic
    actual_gap_ns: int = 0       # observed idle duration (retrospective)


# ---------------------------------------------------------------------------
# HostDiagV2 raw trace column names (legacy compat)
# ---------------------------------------------------------------------------

HOSTDIAG_COLUMNS_V2 = [
    "pid", "tid", "source", "destination",
    "size_mb", "latency_us", "bw_gbps",
    "start_ns", "end_ns", "wall_start_ns", "wall_end_ns",
]

# FlowGap extended columns (21 columns)
FLOWGAP_COLUMNS = [
    "pid", "tid",
    "src_dev", "dst_dev", "src_numa", "dst_numa",
    "size_mb", "latency_us", "bw_gbps",
    "start_ns", "end_ns",
    "wall_start_ns", "wall_end_ns",
    "direction", "async_flag", "api_type",
    "stream_id",
    "path_id", "link_bitmap",
    "quality_flags",
]

# Aggregated trace columns
AGG_COLUMNS = [
    "window_start_ns", "window_end_ns",
    "src_dev", "dst_dev", "src_numa", "dst_numa",
    "path_id", "link_bitmap",
    "bytes_mb", "bw_gbps",
    "wall_start_ns", "wall_end_ns",
    "duration_ms", "packet_count",
    "direction",
]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_event(event: FlowEvent) -> List[str]:
    """Return list of validation errors (empty = valid)."""
    errors = []
    if event.ts_exit_ns < event.ts_enter_ns:
        errors.append("ts_exit_ns < ts_enter_ns")
    if event.size <= 0:
        errors.append("size <= 0")
    if event.direction not in (d.value for d in Direction):
        errors.append(f"invalid direction: {event.direction}")
    if event.src_dev >= 0xFFFFFFF0 and event.src_dev != HOST_DEVICE_ID:
        errors.append(f"invalid src_dev: {event.src_dev}")
    if event.dst_dev >= 0xFFFFFFF0 and event.dst_dev != HOST_DEVICE_ID:
        errors.append(f"invalid dst_dev: {event.dst_dev}")
    return errors
