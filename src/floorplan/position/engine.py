"""Position engine — orchestrates trilateration and tracking filters.

Combines range measurements from the ranging engine with reference point
positions to compute and track device positions over time.
"""

from __future__ import annotations

import logging
import time

from floorplan.config.models import ReferencePoint
from floorplan.models import Position
from floorplan.position.kalman import KalmanConfig, KalmanTracker
from floorplan.position.particle import ParticleFilter
from floorplan.position.trilateration import RangeInput, TrilaterationSolver
from floorplan.ranging.engine import RangingResult

logger = logging.getLogger(__name__)


class PositionEngine:
    """Computes device positions from range measurements.

    Workflow:
    1. Collect range measurements from multiple reference points for a device.
    2. Run trilateration to get a position fix.
    3. Feed the fix through a Kalman or particle filter for smooth tracking.
    """

    def __init__(
        self,
        reference_points: list[ReferencePoint],
        filter_type: str = "kalman",
        use_3d: bool = False,
        kalman_config: KalmanConfig | None = None,
        particle_count: int = 500,
    ) -> None:
        self.reference_points = {rp.mac.lower(): rp for rp in reference_points}
        self.filter_type = filter_type
        self.trilateration = TrilaterationSolver(use_3d=use_3d)

        self._kalman_config = kalman_config or KalmanConfig()
        self._particle_count = particle_count

        # Per-device filters
        self._kalman_filters: dict[str, KalmanTracker] = {}
        self._particle_filters: dict[str, ParticleFilter] = {}

        # Pending measurements buffer: device_id -> list of (ref_mac, distance, std_dev, timestamp)
        self._pending: dict[str, list[tuple[str, float, float, float]]] = {}

    def add_measurement(
        self,
        device_id: str,
        ref_mac: str,
        distance_m: float,
        std_dev_m: float = 1.0,
        timestamp: float = 0.0,
    ) -> Position | None:
        """Add a range measurement and attempt position computation.

        Buffers measurements until enough reference points are available for
        trilateration, then computes position and updates the tracking filter.

        Args:
            device_id: Identifier for the device being tracked.
            ref_mac: MAC address of the reference point.
            distance_m: Measured distance to the reference point.
            std_dev_m: Standard deviation of the measurement.
            timestamp: Measurement timestamp.

        Returns:
            Updated position if enough measurements are available, else None.
        """
        ref_mac = ref_mac.lower()
        if ref_mac not in self.reference_points:
            logger.warning("Unknown reference point: %s", ref_mac)
            return None

        ts = timestamp or time.time()

        if device_id not in self._pending:
            self._pending[device_id] = []

        # Replace existing measurement from same reference point
        self._pending[device_id] = [m for m in self._pending[device_id] if m[0] != ref_mac]
        self._pending[device_id].append((ref_mac, distance_m, std_dev_m, ts))

        # Expire old measurements (>5 seconds)
        cutoff = ts - 5.0
        self._pending[device_id] = [m for m in self._pending[device_id] if m[3] >= cutoff]

        # Need at least 3 reference points for 2D trilateration
        if len(self._pending[device_id]) >= 3:
            return self._compute_position(device_id, ts)

        # With fewer refs, update Kalman filter with individual range measurements
        rp = self.reference_points[ref_mac]
        return self._update_filter_range(device_id, rp, distance_m, std_dev_m, ts)

    def process_ranging_result(self, device_id: str, result: RangingResult) -> Position | None:
        """Process a RangingResult from the ranging engine."""
        return self.add_measurement(
            device_id=device_id,
            ref_mac=result.target_mac,
            distance_m=result.distance_m,
            std_dev_m=result.std_dev_m,
            timestamp=result.timestamp,
        )

    def get_position(self, device_id: str) -> Position | None:
        """Get the current estimated position for a device."""
        if self.filter_type == "particle":
            pf = self._particle_filters.get(device_id)
            return pf.position if pf else None
        kf = self._kalman_filters.get(device_id)
        return kf.position if kf else None

    def _compute_position(self, device_id: str, timestamp: float) -> Position:
        """Run trilateration and update filter."""
        measurements = self._pending[device_id]
        ranges: list[RangeInput] = []

        for ref_mac, distance_m, std_dev_m, _ in measurements:
            rp = self.reference_points[ref_mac]
            weight = 1.0 / max(std_dev_m**2, 0.01)
            ranges.append(
                RangeInput(
                    ref_x=rp.x,
                    ref_y=rp.y,
                    ref_z=rp.z,
                    distance_m=distance_m,
                    weight=weight,
                )
            )

        try:
            trilat_pos = self.trilateration.solve(ranges)
        except Exception as e:
            logger.error("Trilateration failed for %s: %s", device_id, e)
            return self.get_position(device_id) or Position(0, 0, uncertainty_m=float("inf"))

        # Update tracking filter with trilaterated position
        return self._update_filter_position(device_id, trilat_pos, timestamp)

    def _update_filter_position(self, device_id: str, pos: Position, timestamp: float) -> Position:
        """Update the tracking filter with a trilaterated position."""
        if self.filter_type == "particle":
            pf = self._get_or_create_particle(device_id, pos, timestamp)
            # Use range updates from trilateration implicitly
            return pf.position
        else:
            kf = self._get_or_create_kalman(device_id, pos, timestamp)
            return kf.update_position(
                pos.x,
                pos.y,
                measurement_noise=max(pos.uncertainty_m**2, 0.1),
                timestamp=timestamp,
            )

    def _update_filter_range(
        self,
        device_id: str,
        rp: ReferencePoint,
        distance_m: float,
        std_dev_m: float,
        timestamp: float,
    ) -> Position | None:
        """Update the tracking filter with a single range measurement."""
        if self.filter_type == "particle":
            pf = self._particle_filters.get(device_id)
            if pf is None:
                return None  # Need initial position from trilateration
            return pf.update_range(rp.x, rp.y, distance_m, timestamp)
        else:
            kf = self._kalman_filters.get(device_id)
            if kf is None:
                return None
            return kf.update_range(
                rp.x,
                rp.y,
                distance_m,
                measurement_noise=max(std_dev_m**2, 0.1),
                timestamp=timestamp,
            )

    def _get_or_create_kalman(
        self, device_id: str, initial_pos: Position, timestamp: float
    ) -> KalmanTracker:
        kf = self._kalman_filters.get(device_id)
        if kf is None:
            kf = KalmanTracker(config=self._kalman_config)
            kf.initialize(initial_pos.x, initial_pos.y, timestamp)
            self._kalman_filters[device_id] = kf
        return kf

    def _get_or_create_particle(
        self, device_id: str, initial_pos: Position, timestamp: float
    ) -> ParticleFilter:
        pf = self._particle_filters.get(device_id)
        if pf is None:
            pf = ParticleFilter(num_particles=self._particle_count)
            pf.initialize(initial_pos.x, initial_pos.y, timestamp=timestamp)
            self._particle_filters[device_id] = pf
        return pf

    def remove_device(self, device_id: str) -> None:
        """Remove a device from tracking."""
        self._kalman_filters.pop(device_id, None)
        self._particle_filters.pop(device_id, None)
        self._pending.pop(device_id, None)
