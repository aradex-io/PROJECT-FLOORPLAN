"""Tracked device state management."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from floorplan.models import Position, TrackState, Velocity


@dataclass
class TrackedDevice:
    """Full state of a tracked device including position, identity, and history."""

    device_id: str
    mac: str
    position: Position = field(default_factory=lambda: Position(0, 0))
    velocity: Velocity = field(default_factory=Velocity)
    state: TrackState = TrackState.ACTIVE

    # MAC randomization tracking
    mac_history: list[str] = field(default_factory=list)
    fingerprint_hash: str = ""

    # Track history
    track_history: list[tuple[float, Position]] = field(default_factory=list)
    max_history: int = 1000

    # Timing
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_position_update: float = 0.0

    # Quality
    confidence: float = 0.0
    measurement_count: int = 0

    # Zone tracking
    current_zones: set[str] = field(default_factory=set)
    zone_enter_times: dict[str, float] = field(default_factory=dict)

    def update_position(self, pos: Position, timestamp: float = 0.0) -> None:
        """Update the device's position and record in history."""
        ts = timestamp or time.time()
        self.position = pos
        self.last_position_update = ts
        self.last_seen = ts
        self.measurement_count += 1
        self.state = TrackState.ACTIVE

        self.track_history.append((ts, pos))
        if len(self.track_history) > self.max_history:
            self.track_history = self.track_history[-self.max_history:]

        # Update confidence based on position uncertainty
        if pos.uncertainty_m < 1.0:
            self.confidence = min(1.0, 0.9)
        elif pos.uncertainty_m < 3.0:
            self.confidence = 0.6
        elif pos.uncertainty_m < 10.0:
            self.confidence = 0.3
        else:
            self.confidence = 0.1

    def update_mac(self, new_mac: str) -> None:
        """Record a MAC address change (randomization detected)."""
        new_mac = new_mac.lower()
        if new_mac != self.mac:
            if self.mac not in self.mac_history:
                self.mac_history.append(self.mac)
            self.mac = new_mac

    def mark_stale(self, timeout_s: float = 30.0) -> bool:
        """Mark as stale if not seen recently. Returns True if state changed."""
        if self.state == TrackState.ACTIVE:
            elapsed = time.time() - self.last_seen
            if elapsed > timeout_s * 3:
                self.state = TrackState.LOST
                return True
            elif elapsed > timeout_s:
                self.state = TrackState.STALE
                return True
        return False

    def dwell_time_in_zone(self, zone_name: str) -> float:
        """Get current dwell time in a zone (seconds)."""
        enter_time = self.zone_enter_times.get(zone_name)
        if enter_time is None:
            return 0.0
        return time.time() - enter_time

    def to_dict(self) -> dict:
        """Serialize to dictionary for API/WebSocket transmission."""
        return {
            "device_id": self.device_id,
            "mac": self.mac,
            "position": {"x": self.position.x, "y": self.position.y, "z": self.position.z},
            "uncertainty_m": self.position.uncertainty_m,
            "velocity": {"vx": self.velocity.vx, "vy": self.velocity.vy},
            "speed_mps": self.velocity.speed,
            "state": self.state.name.lower(),
            "confidence": self.confidence,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "mac_history": self.mac_history,
            "current_zones": list(self.current_zones),
            "measurement_count": self.measurement_count,
        }
