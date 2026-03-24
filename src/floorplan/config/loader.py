"""YAML configuration loader and saver."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from floorplan.config.models import FloorPlan, ReferencePoint, SiteConfig, ZoneConfig


def _ref_point_from_dict(d: dict[str, Any]) -> ReferencePoint:
    return ReferencePoint(
        mac=d["mac"],
        channel=d["channel"],
        x=float(d["x"]),
        y=float(d["y"]),
        z=float(d.get("z", 0.0)),
        label=d.get("label"),
        calibration_profile=d.get("calibration_profile"),
    )


def _zone_from_dict(d: dict[str, Any]) -> ZoneConfig:
    vertices = [(float(v[0]), float(v[1])) for v in d["vertices"]]
    return ZoneConfig(
        name=d["name"],
        zone_type=d.get("zone_type", "authorized"),
        vertices=vertices,
        floor=d.get("floor", 0),
        alert_on_enter=d.get("alert_on_enter", False),
        alert_on_exit=d.get("alert_on_exit", False),
        alert_on_dwell=d.get("alert_on_dwell", False),
        max_dwell_time_s=float(d.get("max_dwell_time_s", 0.0)),
    )


def _floor_plan_from_dict(d: dict[str, Any]) -> FloorPlan:
    cal_points = []
    for cp in d.get("calibration_points", []):
        pixel = (float(cp["pixel"][0]), float(cp["pixel"][1]))
        world = (float(cp["world"][0]), float(cp["world"][1]))
        cal_points.append((pixel, world))
    return FloorPlan(
        image_path=d["image_path"],
        floor=d.get("floor", 0),
        calibration_points=cal_points,
        width_m=float(d.get("width_m", 0.0)),
        height_m=float(d.get("height_m", 0.0)),
    )


def load_config(path: str | Path) -> SiteConfig:
    """Load a site configuration from a YAML file."""
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)

    ref_points = [_ref_point_from_dict(rp) for rp in data.get("reference_points", [])]
    zones = [_zone_from_dict(z) for z in data.get("zones", [])]
    floor_plans = [_floor_plan_from_dict(fp) for fp in data.get("floor_plans", [])]

    return SiteConfig(
        name=data["name"],
        description=data.get("description", ""),
        reference_points=ref_points,
        zones=zones,
        floor_plans=floor_plans,
        interface=data.get("interface", "wlan0"),
        scan_interval_s=float(data.get("scan_interval_s", 1.0)),
        tracking_mode=data.get("tracking_mode", "active"),
        burst_config=data.get("burst_config", "fast"),
        webhook_url=data.get("webhook_url"),
        alert_cooldown_s=float(data.get("alert_cooldown_s", 60.0)),
    )


def save_config(config: SiteConfig, path: str | Path) -> None:
    """Save a site configuration to a YAML file."""
    path = Path(path)
    data: dict[str, Any] = {
        "name": config.name,
        "description": config.description,
        "interface": config.interface,
        "scan_interval_s": config.scan_interval_s,
        "tracking_mode": config.tracking_mode,
        "burst_config": config.burst_config,
        "alert_cooldown_s": config.alert_cooldown_s,
    }
    if config.webhook_url:
        data["webhook_url"] = config.webhook_url

    if config.reference_points:
        data["reference_points"] = [
            {
                "mac": rp.mac,
                "channel": rp.channel,
                "x": rp.x,
                "y": rp.y,
                "z": rp.z,
                **({"label": rp.label} if rp.label else {}),
                **(
                    {"calibration_profile": rp.calibration_profile}
                    if rp.calibration_profile
                    else {}
                ),
            }
            for rp in config.reference_points
        ]

    if config.zones:
        data["zones"] = [
            {
                "name": z.name,
                "zone_type": z.zone_type,
                "vertices": [list(v) for v in z.vertices],
                "floor": z.floor,
                "alert_on_enter": z.alert_on_enter,
                "alert_on_exit": z.alert_on_exit,
                "alert_on_dwell": z.alert_on_dwell,
                "max_dwell_time_s": z.max_dwell_time_s,
            }
            for z in config.zones
        ]

    if config.floor_plans:
        data["floor_plans"] = [
            {
                "image_path": fp.image_path,
                "floor": fp.floor,
                "calibration_points": [
                    {"pixel": list(cp[0]), "world": list(cp[1])}
                    for cp in fp.calibration_points
                ],
                "width_m": fp.width_m,
                "height_m": fp.height_m,
            }
            for fp in config.floor_plans
        ]

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
