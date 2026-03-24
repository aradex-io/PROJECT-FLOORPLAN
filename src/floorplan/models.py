"""Core data models used across FLOORPLAN components."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class DeviceType(Enum):
    """Classification of discovered Wi-Fi devices."""

    ACCESS_POINT = auto()
    STATION = auto()
    UNKNOWN = auto()


class TrackState(Enum):
    """Lifecycle state of a tracked device."""

    ACTIVE = auto()
    STALE = auto()
    LOST = auto()


@dataclass(frozen=True)
class Position:
    """2D/3D position with uncertainty estimate."""

    x: float
    y: float
    z: float = 0.0
    uncertainty_m: float = 0.0

    def distance_to(self, other: Position) -> float:
        """Euclidean distance to another position."""
        return (
            (self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2
        ) ** 0.5


@dataclass(frozen=True)
class Velocity:
    """Velocity vector in m/s."""

    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0

    @property
    def speed(self) -> float:
        return (self.vx**2 + self.vy**2 + self.vz**2) ** 0.5


@dataclass
class RangingMeasurement:
    """Single FTM ranging measurement result."""

    target_mac: str
    distance_cm: float
    std_dev_cm: float
    rssi_dbm: int
    rtt_ns: float
    timestamp: float = field(default_factory=time.time)
    burst_index: int = 0
    ftms_per_burst: int = 0
    is_nlos: Optional[bool] = None
    nlos_confidence: float = 0.0


@dataclass
class BurstConfig:
    """FTM burst measurement configuration."""

    num_bursts: int = 4
    ftms_per_burst: int = 8
    burst_period_ms: int = 200
    min_delta_ftm: int = 0
    channel: int = 0
    bandwidth: int = 0  # 0=auto, 20, 40, 80, 160 MHz

    @classmethod
    def fast(cls) -> BurstConfig:
        """Fast config for real-time tracking."""
        return cls(num_bursts=1, ftms_per_burst=4, burst_period_ms=100)

    @classmethod
    def accurate(cls) -> BurstConfig:
        """High-accuracy config for surveying."""
        return cls(num_bursts=8, ftms_per_burst=8, burst_period_ms=500)


@dataclass
class FTMCapabilities:
    """FTM capabilities of a Wi-Fi device."""

    supports_ftm_initiator: bool = False
    supports_ftm_responder: bool = False
    max_bursts: int = 0
    max_ftms_per_burst: int = 0
    supports_asap: bool = False
    supported_bandwidths: list[int] = field(default_factory=list)


@dataclass
class DiscoveredDevice:
    """A Wi-Fi device discovered via scanning."""

    mac: str
    ssid: Optional[str] = None
    channel: int = 0
    rssi_dbm: int = -100
    device_type: DeviceType = DeviceType.UNKNOWN
    ftm_capable: bool = False
    ftm_caps: Optional[FTMCapabilities] = None
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    supported_rates: list[float] = field(default_factory=list)
    ht_capable: bool = False
    vht_capable: bool = False
    he_capable: bool = False


@dataclass
class ZoneEvent:
    """Event generated when a device enters/exits a zone."""

    device_id: str
    zone_name: str
    event_type: str  # "enter" | "exit" | "dwell"
    position: Position
    timestamp: float = field(default_factory=time.time)
    dwell_time_s: Optional[float] = None
