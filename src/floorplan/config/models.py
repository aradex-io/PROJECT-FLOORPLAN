"""Configuration data models for site definition and deployment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReferencePoint:
    """A known FTM responder used as a positioning reference."""

    mac: str
    channel: int
    x: float  # meters from origin
    y: float
    z: float = 0.0
    label: Optional[str] = None
    calibration_profile: Optional[str] = None


@dataclass
class ZoneConfig:
    """A named polygonal zone on the floor plan for geofencing."""

    name: str
    zone_type: str  # "authorized", "restricted", "sensitive"
    vertices: list[tuple[float, float]]  # polygon vertices in meters
    floor: int = 0
    alert_on_enter: bool = False
    alert_on_exit: bool = False
    alert_on_dwell: bool = False
    max_dwell_time_s: float = 0.0  # 0 = no dwell alert


@dataclass
class FloorPlan:
    """Floor plan image with coordinate calibration."""

    image_path: str
    floor: int = 0
    # Calibration: 3+ pixel-to-real-world coordinate mappings
    calibration_points: list[tuple[tuple[float, float], tuple[float, float]]] = field(
        default_factory=list
    )
    # Computed affine transform coefficients (populated after calibration)
    transform_matrix: Optional[list[list[float]]] = None
    width_m: float = 0.0
    height_m: float = 0.0


@dataclass
class SiteConfig:
    """Complete site configuration for a FLOORPLAN deployment."""

    name: str
    description: str = ""
    reference_points: list[ReferencePoint] = field(default_factory=list)
    zones: list[ZoneConfig] = field(default_factory=list)
    floor_plans: list[FloorPlan] = field(default_factory=list)
    # Ranging engine settings
    interface: str = "wlan0"
    scan_interval_s: float = 1.0
    tracking_mode: str = "active"  # "active", "passive", "hybrid"
    burst_config: str = "fast"  # "fast", "accurate", or custom
    # Alert settings
    webhook_url: Optional[str] = None
    alert_cooldown_s: float = 60.0
