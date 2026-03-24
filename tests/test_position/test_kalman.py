"""Tests for the Kalman filter tracker."""

import numpy as np

from floorplan.position.kalman import KalmanConfig, KalmanTracker


class TestKalmanTracker:
    """Test EKF position tracking."""

    def test_initialization(self):
        """Filter should initialize at given position."""
        kf = KalmanTracker()
        kf.initialize(5.0, 3.0, timestamp=0.0)

        pos = kf.position
        assert abs(pos.x - 5.0) < 0.01
        assert abs(pos.y - 3.0) < 0.01

    def test_prediction_moves_with_velocity(self):
        """Prediction should extrapolate position using velocity."""
        kf = KalmanTracker()
        kf.initialize(0.0, 0.0, timestamp=0.0)
        # Manually set velocity
        kf._state[2] = 1.0  # vx = 1 m/s
        kf._state[3] = 0.5  # vy = 0.5 m/s

        pos = kf.predict(timestamp=2.0)
        assert abs(pos.x - 2.0) < 0.5
        assert abs(pos.y - 1.0) < 0.5

    def test_range_update_converges(self):
        """Repeated range updates should converge to true position."""
        kf = KalmanTracker(config=KalmanConfig(measurement_noise=0.5))
        kf.initialize(0.0, 0.0, timestamp=0.0)

        # True position at (5, 5), reference at (0, 0)
        true_x, true_y = 5.0, 5.0
        # Feed many measurements from multiple reference points
        refs = [(0, 0), (10, 0), (0, 10)]
        for i in range(50):
            ts = float(i) * 0.1
            for rx, ry in refs:
                d = np.sqrt((true_x - rx) ** 2 + (true_y - ry) ** 2)
                noise = np.random.normal(0, 0.3)
                kf.update_range(rx, ry, d + noise, timestamp=ts)

        pos = kf.position
        error = np.sqrt((pos.x - true_x) ** 2 + (pos.y - true_y) ** 2)
        assert error < 1.0  # Should converge to within 1m

    def test_position_update(self):
        """Direct position update should snap to measurement."""
        kf = KalmanTracker(config=KalmanConfig(measurement_noise=0.1))
        kf.initialize(0.0, 0.0, timestamp=0.0)

        kf.update_position(5.0, 3.0, timestamp=1.0)
        pos = kf.position
        # Should be close to the measurement
        assert abs(pos.x - 5.0) < 1.0
        assert abs(pos.y - 3.0) < 1.0

    def test_uncertainty_decreases(self):
        """Uncertainty should decrease with more measurements."""
        kf = KalmanTracker()
        kf.initialize(5.0, 5.0, timestamp=0.0)
        initial_unc = kf.position.uncertainty_m

        for i in range(20):
            kf.update_position(5.0, 5.0, timestamp=float(i) * 0.1)

        final_unc = kf.position.uncertainty_m
        assert final_unc < initial_unc

    def test_reset(self):
        """Reset should clear all state."""
        kf = KalmanTracker()
        kf.initialize(5.0, 5.0, timestamp=0.0)
        kf.reset()

        pos = kf.position
        assert pos.x == 0.0
        assert pos.y == 0.0
