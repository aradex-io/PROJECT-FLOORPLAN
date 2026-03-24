"""Kalman filter for smooth position tracking over time.

State vector: [x, y, vx, vy] — position and velocity in 2D.
Process model: constant velocity with Gaussian process noise.
Measurement model: range measurements from reference points.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np

from floorplan.models import Position, Velocity

logger = logging.getLogger(__name__)


@dataclass
class KalmanConfig:
    """Tuning parameters for the Kalman filter."""

    # Process noise — how erratic is the device's movement?
    process_noise_pos: float = 0.5  # m²/s² position noise
    process_noise_vel: float = 2.0  # m²/s⁴ velocity noise
    # Measurement noise — from Phase 1 characterization
    measurement_noise: float = 1.0  # m² ranging measurement noise
    # Initial state uncertainty
    initial_pos_uncertainty: float = 10.0  # m²
    initial_vel_uncertainty: float = 5.0  # m²/s²


class KalmanTracker:
    """Extended Kalman filter for 2D position tracking from range measurements.

    Tracks [x, y, vx, vy] state using a constant-velocity process model and
    nonlinear range measurement model (distance to known reference points).
    """

    def __init__(self, config: KalmanConfig | None = None) -> None:
        self.config = config or KalmanConfig()

        # State vector [x, y, vx, vy]
        self._state = np.zeros(4)
        # State covariance
        self._P = np.eye(4)
        self._initialized = False
        self._last_update_time: float = 0.0

    @property
    def position(self) -> Position:
        """Current estimated position."""
        uncertainty = float(np.sqrt(self._P[0, 0] + self._P[1, 1]))
        return Position(
            x=float(self._state[0]),
            y=float(self._state[1]),
            uncertainty_m=uncertainty,
        )

    @property
    def velocity(self) -> Velocity:
        """Current estimated velocity."""
        return Velocity(vx=float(self._state[2]), vy=float(self._state[3]))

    def initialize(self, x: float, y: float, timestamp: float | None = None) -> None:
        """Initialize the filter at a known position."""
        c = self.config
        self._state = np.array([x, y, 0.0, 0.0])
        self._P = np.diag(
            [
                c.initial_pos_uncertainty,
                c.initial_pos_uncertainty,
                c.initial_vel_uncertainty,
                c.initial_vel_uncertainty,
            ]
        )
        self._last_update_time = timestamp if timestamp is not None else time.time()
        self._initialized = True

    def predict(self, timestamp: float | None = None) -> Position:
        """Predict state forward to the given timestamp.

        Uses constant-velocity model: x(t+dt) = x(t) + vx*dt.
        """
        if not self._initialized:
            return Position(0, 0, uncertainty_m=float("inf"))

        now = timestamp if timestamp is not None else time.time()
        dt = now - self._last_update_time
        if dt <= 0:
            return self.position

        # State transition matrix
        F = np.eye(4)  # noqa: N806
        F[0, 2] = dt  # x += vx * dt
        F[1, 3] = dt  # y += vy * dt

        # Process noise covariance
        c = self.config
        q_p = c.process_noise_pos
        q_v = c.process_noise_vel
        Q = np.array(  # noqa: N806
            [
                [q_p * dt**3 / 3, 0, q_p * dt**2 / 2, 0],
                [0, q_p * dt**3 / 3, 0, q_p * dt**2 / 2],
                [q_p * dt**2 / 2, 0, q_v * dt, 0],
                [0, q_p * dt**2 / 2, 0, q_v * dt],
            ]
        )

        self._state = F @ self._state
        self._P = F @ self._P @ F.T + Q
        self._last_update_time = now

        return self.position

    def update_range(
        self,
        ref_x: float,
        ref_y: float,
        measured_distance: float,
        measurement_noise: float = 0.0,
        timestamp: float | None = None,
    ) -> Position:
        """Update state with a single range measurement.

        Uses the Extended Kalman Filter (EKF) approach because the measurement
        model h(x) = sqrt((x-rx)² + (y-ry)²) is nonlinear.

        Args:
            ref_x, ref_y: Known position of the reference point.
            measured_distance: Measured distance to reference point (meters).
            measurement_noise: Measurement noise variance (m²). 0 = use default.
            timestamp: Measurement timestamp.
        """
        if not self._initialized:
            self.initialize(ref_x, ref_y, timestamp)
            return self.position

        # Predict to current time
        self.predict(timestamp)

        # Measurement model: h(x) = distance from state to reference
        dx = self._state[0] - ref_x
        dy = self._state[1] - ref_y
        predicted_distance = np.sqrt(dx**2 + dy**2)

        # Avoid division by zero
        if predicted_distance < 1e-6:
            predicted_distance = 1e-6
            dx = 1e-6

        # Jacobian of measurement model
        H = np.array([dx / predicted_distance, dy / predicted_distance, 0.0, 0.0]).reshape(1, 4)  # noqa: N806

        # Innovation (measurement residual)
        innovation = measured_distance - predicted_distance

        # Measurement noise
        R = np.array([[measurement_noise or self.config.measurement_noise]])  # noqa: N806

        # Kalman gain
        S = H @ self._P @ H.T + R  # noqa: N806
        K = self._P @ H.T @ np.linalg.inv(S)  # noqa: N806

        # State update
        self._state = self._state + (K @ np.array([[innovation]])).flatten()

        # Covariance update (Joseph form for numerical stability)
        I_KH = np.eye(4) - K @ H  # noqa: N806
        self._P = I_KH @ self._P @ I_KH.T + K @ R @ K.T

        return self.position

    def update_position(
        self,
        measured_x: float,
        measured_y: float,
        measurement_noise: float = 0.0,
        timestamp: float | None = None,
    ) -> Position:
        """Update state with a direct position measurement.

        Simpler than range update — linear measurement model.
        """
        if not self._initialized:
            self.initialize(measured_x, measured_y, timestamp)
            return self.position

        self.predict(timestamp)

        # Linear measurement model: z = [x, y]
        H = np.array(  # noqa: N806
            [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
            ],
            dtype=float,
        )

        innovation = np.array(
            [
                measured_x - self._state[0],
                measured_y - self._state[1],
            ]
        )

        r = measurement_noise or self.config.measurement_noise
        R = np.eye(2) * r  # noqa: N806

        S = H @ self._P @ H.T + R  # noqa: N806
        K = self._P @ H.T @ np.linalg.inv(S)  # noqa: N806

        self._state = self._state + K @ innovation
        I_KH = np.eye(4) - K @ H  # noqa: N806
        self._P = I_KH @ self._P @ I_KH.T + K @ R @ K.T

        return self.position

    def reset(self) -> None:
        """Reset the filter state."""
        self._state = np.zeros(4)
        self._P = np.eye(4)
        self._initialized = False
        self._last_update_time = 0.0
