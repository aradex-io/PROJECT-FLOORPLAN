"""Track manager — multi-target tracking with zone-based alerting."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from floorplan.config.models import ZoneConfig
from floorplan.models import Position, TrackState, ZoneEvent
from floorplan.tracking.device import TrackedDevice
from floorplan.tracking.fingerprint import DeviceFingerprint, DeviceSignature

logger = logging.getLogger(__name__)


class TrackManager:
    """Manages multiple tracked devices with lifecycle and zone alerting.

    Responsibilities:
    - Create/update/remove tracked devices
    - Handle MAC randomization via fingerprinting
    - Zone-based geofence alerting
    - Periodic staleness checks
    """

    def __init__(
        self,
        zones: list[ZoneConfig] | None = None,
        stale_timeout_s: float = 30.0,
        lost_timeout_s: float = 90.0,
    ) -> None:
        self.zones = {z.name: z for z in (zones or [])}
        self.stale_timeout_s = stale_timeout_s
        self.lost_timeout_s = lost_timeout_s
        self.fingerprinter = DeviceFingerprint()

        self._devices: dict[str, TrackedDevice] = {}
        self._mac_to_device: dict[str, str] = {}  # mac -> device_id
        self._lock = threading.Lock()

        # Event callbacks
        self._zone_callbacks: list[Callable[[ZoneEvent], None]] = []
        self._device_callbacks: list[Callable[[TrackedDevice, str], None]] = []

    def on_zone_event(self, callback: Callable[[ZoneEvent], None]) -> None:
        """Register callback for zone enter/exit/dwell events."""
        self._zone_callbacks.append(callback)

    def on_device_event(self, callback: Callable[[TrackedDevice, str], None]) -> None:
        """Register callback for device lifecycle events (new, lost, etc.)."""
        self._device_callbacks.append(callback)

    def update_position(
        self,
        mac: str,
        position: Position,
        timestamp: float = 0.0,
        signature: DeviceSignature | None = None,
    ) -> TrackedDevice:
        """Update a device's position, creating a new track if needed."""
        mac = mac.lower()
        ts = timestamp or time.time()

        with self._lock:
            device_id = self._resolve_device(mac, signature)
            device = self._devices.get(device_id)

            if device is None:
                device = TrackedDevice(
                    device_id=device_id,
                    mac=mac,
                    first_seen=ts,
                )
                self._devices[device_id] = device
                self._mac_to_device[mac] = device_id
                self._emit_device_event(device, "new")
                logger.info("New device tracked: %s (%s)", device_id, mac)

            device.update_position(position, ts)

            if mac != device.mac:
                device.update_mac(mac)
                self._mac_to_device[mac] = device_id

            if signature:
                self.fingerprinter.register(device_id, signature)
                device.fingerprint_hash = signature.fingerprint

        # Check zone events outside lock
        self._check_zones(device, position, ts)

        return device

    def get_device(self, device_id: str) -> TrackedDevice | None:
        """Get a tracked device by ID."""
        with self._lock:
            return self._devices.get(device_id)

    def get_device_by_mac(self, mac: str) -> TrackedDevice | None:
        """Get a tracked device by MAC address."""
        mac = mac.lower()
        with self._lock:
            device_id = self._mac_to_device.get(mac)
            if device_id:
                return self._devices.get(device_id)
        return None

    def get_all_devices(self) -> list[TrackedDevice]:
        """Get all tracked devices."""
        with self._lock:
            return list(self._devices.values())

    def get_active_devices(self) -> list[TrackedDevice]:
        """Get only active (non-lost) devices."""
        with self._lock:
            return [d for d in self._devices.values() if d.state != TrackState.LOST]

    def cleanup_stale(self) -> list[str]:
        """Mark stale/lost devices. Returns IDs of newly lost devices."""
        lost_ids: list[str] = []
        with self._lock:
            for device in self._devices.values():
                old_state = device.state
                device.mark_stale(self.stale_timeout_s)
                if device.state == TrackState.LOST and old_state != TrackState.LOST:
                    lost_ids.append(device.device_id)

        for device_id in lost_ids:
            device = self._devices.get(device_id)
            if device:
                self._emit_device_event(device, "lost")

        return lost_ids

    def remove_device(self, device_id: str) -> None:
        """Remove a device from tracking."""
        with self._lock:
            device = self._devices.pop(device_id, None)
            if device:
                self._mac_to_device.pop(device.mac, None)
                for mac in device.mac_history:
                    self._mac_to_device.pop(mac, None)

    def _resolve_device(self, mac: str, signature: DeviceSignature | None) -> str:
        """Resolve a MAC to a device ID, handling randomization."""
        # Direct MAC lookup
        existing_id = self._mac_to_device.get(mac)
        if existing_id:
            return existing_id

        # Fingerprint lookup
        if signature:
            matched_id = self.fingerprinter.identify(signature)
            if matched_id:
                return matched_id

        # New device — use MAC as ID
        return mac

    def _check_zones(self, device: TrackedDevice, pos: Position, ts: float) -> None:
        """Check if device has entered/exited any defined zones."""
        for zone_name, zone in self.zones.items():
            inside = self._point_in_polygon(pos.x, pos.y, zone.vertices)
            was_inside = zone_name in device.current_zones

            if inside and not was_inside:
                device.current_zones.add(zone_name)
                device.zone_enter_times[zone_name] = ts
                if zone.alert_on_enter:
                    event = ZoneEvent(
                        device_id=device.device_id,
                        zone_name=zone_name,
                        event_type="enter",
                        position=pos,
                        timestamp=ts,
                    )
                    self._emit_zone_event(event)

            elif not inside and was_inside:
                device.current_zones.discard(zone_name)
                dwell = ts - device.zone_enter_times.pop(zone_name, ts)
                if zone.alert_on_exit:
                    event = ZoneEvent(
                        device_id=device.device_id,
                        zone_name=zone_name,
                        event_type="exit",
                        position=pos,
                        timestamp=ts,
                        dwell_time_s=dwell,
                    )
                    self._emit_zone_event(event)

            elif inside and was_inside and zone.alert_on_dwell:
                dwell = device.dwell_time_in_zone(zone_name)
                if zone.max_dwell_time_s > 0 and dwell > zone.max_dwell_time_s:
                    event = ZoneEvent(
                        device_id=device.device_id,
                        zone_name=zone_name,
                        event_type="dwell",
                        position=pos,
                        timestamp=ts,
                        dwell_time_s=dwell,
                    )
                    self._emit_zone_event(event)

    @staticmethod
    def _point_in_polygon(x: float, y: float, vertices: list[tuple[float, float]]) -> bool:
        """Ray-casting point-in-polygon test."""
        n = len(vertices)
        if n < 3:
            return False

        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = vertices[i]
            xj, yj = vertices[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

    def _emit_zone_event(self, event: ZoneEvent) -> None:
        for cb in self._zone_callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error("Zone event callback error: %s", e)

    def _emit_device_event(self, device: TrackedDevice, event_type: str) -> None:
        for cb in self._device_callbacks:
            try:
                cb(device, event_type)
            except Exception as e:
                logger.error("Device event callback error: %s", e)
