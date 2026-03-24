"""Tests for the particle filter."""

import numpy as np

from floorplan.position.particle import ParticleFilter


class TestParticleFilter:
    """Test particle filter position tracking."""

    def test_initialization(self):
        """Particles should cluster around initialization point."""
        pf = ParticleFilter(num_particles=200)
        pf.initialize(5.0, 3.0, spread=1.0, timestamp=0.0)

        pos = pf.position
        assert abs(pos.x - 5.0) < 2.0
        assert abs(pos.y - 3.0) < 2.0

    def test_range_update_converges(self):
        """Repeated range updates from multiple refs should converge."""
        np.random.seed(42)
        pf = ParticleFilter(num_particles=500, measurement_noise=0.5)
        pf.initialize(0.0, 0.0, spread=10.0, timestamp=0.0)

        true_x, true_y = 5.0, 5.0
        refs = [(0, 0), (10, 0), (0, 10), (10, 10)]

        for i in range(30):
            ts = float(i) * 0.2
            for rx, ry in refs:
                d = np.sqrt((true_x - rx) ** 2 + (true_y - ry) ** 2)
                noise = np.random.normal(0, 0.3)
                pf.update_range(rx, ry, d + noise, timestamp=ts)

        pos = pf.position
        error = np.sqrt((pos.x - true_x) ** 2 + (pos.y - true_y) ** 2)
        assert error < 2.0

    def test_bounds_constraint(self):
        """Particles should stay within bounds."""
        pf = ParticleFilter(num_particles=100, bounds=(0, 0, 10, 10))
        pf.initialize(5.0, 5.0, spread=20.0, timestamp=0.0)

        # All particles should be within bounds
        assert np.all(pf._particles[:, 0] >= 0)
        assert np.all(pf._particles[:, 0] <= 10)
        assert np.all(pf._particles[:, 1] >= 0)
        assert np.all(pf._particles[:, 1] <= 10)

    def test_uncertainty_with_measurements(self):
        """Uncertainty should decrease as particles converge."""
        np.random.seed(42)
        pf = ParticleFilter(num_particles=300, measurement_noise=0.5)
        pf.initialize(5.0, 5.0, spread=5.0, timestamp=0.0)
        initial_unc = pf.position.uncertainty_m

        for i in range(20):
            pf.update_range(0, 0, np.sqrt(50), timestamp=float(i) * 0.1)
            pf.update_range(10, 0, np.sqrt(50), timestamp=float(i) * 0.1)
            pf.update_range(0, 10, np.sqrt(50), timestamp=float(i) * 0.1)

        final_unc = pf.position.uncertainty_m
        assert final_unc < initial_unc

    def test_reset(self):
        """Reset should clear particle state."""
        pf = ParticleFilter(num_particles=100)
        pf.initialize(5.0, 5.0, timestamp=0.0)
        pf.reset()

        pos = pf.position
        assert pos.uncertainty_m == float("inf")
