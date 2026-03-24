"""Particle filter for position tracking — handles non-Gaussian noise and NLOS.

Better than Kalman for multimodal distributions and environments with heavy
NLOS. More computationally expensive but more robust.
"""

from __future__ import annotations

import logging

import numpy as np

from floorplan.models import Position

logger = logging.getLogger(__name__)


class ParticleFilter:
    """Sequential Monte Carlo (particle) filter for 2D position tracking.

    Each particle represents a hypothesis about the device's position and
    velocity. Particles are weighted by how well they explain the observed
    range measurements, then resampled.
    """

    def __init__(
        self,
        num_particles: int = 500,
        process_noise_pos: float = 0.3,
        process_noise_vel: float = 1.0,
        measurement_noise: float = 1.0,
        bounds: tuple[float, float, float, float] | None = None,
    ) -> None:
        """
        Args:
            num_particles: Number of particles to maintain.
            process_noise_pos: Std dev of position process noise (m).
            process_noise_vel: Std dev of velocity process noise (m/s).
            measurement_noise: Std dev of range measurement noise (m).
            bounds: Optional (x_min, y_min, x_max, y_max) to constrain particles.
        """
        self.num_particles = num_particles
        self.process_noise_pos = process_noise_pos
        self.process_noise_vel = process_noise_vel
        self.measurement_noise = measurement_noise
        self.bounds = bounds

        # Particles: [x, y, vx, vy] for each particle
        self._particles = np.zeros((num_particles, 4))
        self._weights = np.ones(num_particles) / num_particles
        self._initialized = False
        self._last_time: float = 0.0

    @property
    def position(self) -> Position:
        """Weighted mean position estimate."""
        if not self._initialized:
            return Position(0, 0, uncertainty_m=float("inf"))

        mean_x = float(np.average(self._particles[:, 0], weights=self._weights))
        mean_y = float(np.average(self._particles[:, 1], weights=self._weights))

        # Uncertainty: weighted standard deviation
        var_x = float(
            np.average((self._particles[:, 0] - mean_x) ** 2, weights=self._weights)
        )
        var_y = float(
            np.average((self._particles[:, 1] - mean_y) ** 2, weights=self._weights)
        )
        uncertainty = float(np.sqrt(var_x + var_y))

        return Position(x=mean_x, y=mean_y, uncertainty_m=uncertainty)

    def initialize(
        self, x: float, y: float, spread: float = 5.0, timestamp: float = 0.0
    ) -> None:
        """Initialize particles around a position estimate."""
        self._particles[:, 0] = np.random.normal(x, spread, self.num_particles)
        self._particles[:, 1] = np.random.normal(y, spread, self.num_particles)
        self._particles[:, 2] = np.random.normal(0, 0.5, self.num_particles)
        self._particles[:, 3] = np.random.normal(0, 0.5, self.num_particles)
        self._weights = np.ones(self.num_particles) / self.num_particles
        self._last_time = timestamp
        self._initialized = True
        self._apply_bounds()

    def predict(self, timestamp: float) -> None:
        """Propagate particles forward in time."""
        if not self._initialized:
            return

        dt = timestamp - self._last_time
        if dt <= 0:
            return

        # Constant velocity + noise
        self._particles[:, 0] += (
            self._particles[:, 2] * dt
            + np.random.normal(0, self.process_noise_pos * dt, self.num_particles)
        )
        self._particles[:, 1] += (
            self._particles[:, 3] * dt
            + np.random.normal(0, self.process_noise_pos * dt, self.num_particles)
        )
        self._particles[:, 2] += np.random.normal(
            0, self.process_noise_vel * dt, self.num_particles
        )
        self._particles[:, 3] += np.random.normal(
            0, self.process_noise_vel * dt, self.num_particles
        )

        self._last_time = timestamp
        self._apply_bounds()

    def update_range(
        self,
        ref_x: float,
        ref_y: float,
        measured_distance: float,
        timestamp: float = 0.0,
    ) -> Position:
        """Update particle weights based on a range measurement."""
        if not self._initialized:
            self.initialize(ref_x, ref_y, spread=measured_distance, timestamp=timestamp)
            return self.position

        self.predict(timestamp)

        # Compute expected distance from each particle to reference
        dx = self._particles[:, 0] - ref_x
        dy = self._particles[:, 1] - ref_y
        expected_dists = np.sqrt(dx**2 + dy**2)

        # Weight by Gaussian likelihood
        errors = measured_distance - expected_dists
        sigma = self.measurement_noise
        likelihoods = np.exp(-0.5 * (errors / sigma) ** 2) / (
            sigma * np.sqrt(2 * np.pi)
        )

        # Update weights
        self._weights *= likelihoods
        weight_sum = self._weights.sum()
        if weight_sum > 0:
            self._weights /= weight_sum
        else:
            # All particles have zero weight — reinitialize
            logger.warning("Particle filter weight collapse — reinitializing")
            pos = self.position
            self.initialize(pos.x, pos.y, spread=self.measurement_noise * 3, timestamp=timestamp)
            return self.position

        # Resample if effective particle count is too low
        n_eff = 1.0 / np.sum(self._weights**2)
        if n_eff < self.num_particles / 2:
            self._resample()

        return self.position

    def _resample(self) -> None:
        """Systematic resampling of particles."""
        n = self.num_particles
        positions = np.cumsum(self._weights)
        positions[-1] = 1.0  # ensure sum is exactly 1

        start = np.random.uniform(0, 1.0 / n)
        points = start + np.arange(n) / n

        indices = np.searchsorted(positions, points)
        indices = np.clip(indices, 0, n - 1)

        self._particles = self._particles[indices].copy()
        self._weights = np.ones(n) / n

    def _apply_bounds(self) -> None:
        """Clip particles to spatial bounds if configured."""
        if self.bounds is None:
            return
        x_min, y_min, x_max, y_max = self.bounds
        self._particles[:, 0] = np.clip(self._particles[:, 0], x_min, x_max)
        self._particles[:, 1] = np.clip(self._particles[:, 1], y_min, y_max)

    def reset(self) -> None:
        """Reset filter state."""
        self._particles = np.zeros((self.num_particles, 4))
        self._weights = np.ones(self.num_particles) / self.num_particles
        self._initialized = False
