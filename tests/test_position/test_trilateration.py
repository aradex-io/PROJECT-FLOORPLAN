"""Tests for the trilateration solver."""

import numpy as np
import pytest

from floorplan.position.trilateration import RangeInput, TrilaterationSolver


class TestTrilaterationSolver:
    """Test WLS trilateration with known geometries."""

    def test_perfect_triangle(self):
        """Three reference points with exact distances should give exact position."""
        solver = TrilaterationSolver(use_3d=False)

        # Target at (5, 5), refs at corners of a 10x10 square
        target_x, target_y = 5.0, 5.0
        refs = [
            (0.0, 0.0),
            (10.0, 0.0),
            (0.0, 10.0),
        ]
        ranges = []
        for rx, ry in refs:
            d = np.sqrt((target_x - rx) ** 2 + (target_y - ry) ** 2)
            ranges.append(RangeInput(ref_x=rx, ref_y=ry, ref_z=0, distance_m=d))

        pos = solver.solve(ranges)
        assert abs(pos.x - target_x) < 0.01
        assert abs(pos.y - target_y) < 0.01

    def test_four_refs_overdetermined(self):
        """Four reference points (overdetermined) should still converge."""
        solver = TrilaterationSolver(use_3d=False)

        target_x, target_y = 7.0, 3.0
        refs = [(0, 0), (10, 0), (10, 10), (0, 10)]
        ranges = []
        for rx, ry in refs:
            d = np.sqrt((target_x - rx) ** 2 + (target_y - ry) ** 2)
            ranges.append(RangeInput(ref_x=rx, ref_y=ry, ref_z=0, distance_m=d))

        pos = solver.solve(ranges)
        assert abs(pos.x - target_x) < 0.01
        assert abs(pos.y - target_y) < 0.01

    def test_noisy_measurements(self):
        """Noisy distances should produce position with reasonable uncertainty."""
        solver = TrilaterationSolver(use_3d=False)
        np.random.seed(42)

        target_x, target_y = 5.0, 5.0
        refs = [(0, 0), (10, 0), (0, 10), (10, 10)]
        ranges = []
        for rx, ry in refs:
            true_d = np.sqrt((target_x - rx) ** 2 + (target_y - ry) ** 2)
            noisy_d = true_d + np.random.normal(0, 0.5)  # 0.5m noise
            ranges.append(RangeInput(ref_x=rx, ref_y=ry, ref_z=0, distance_m=noisy_d))

        pos = solver.solve(ranges)
        error = np.sqrt((pos.x - target_x) ** 2 + (pos.y - target_y) ** 2)
        assert error < 2.0  # should be within 2m with 0.5m noise

    def test_weighted_measurements(self):
        """Higher-weight measurements should have more influence."""
        solver = TrilaterationSolver(use_3d=False)

        target_x, target_y = 5.0, 5.0
        # Good measurement from (0,0) with weight 10
        # Bad measurement from (10,0) with wrong distance and weight 0.1
        ranges = [
            RangeInput(ref_x=0, ref_y=0, ref_z=0, distance_m=np.sqrt(50), weight=10.0),
            RangeInput(ref_x=10, ref_y=0, ref_z=0, distance_m=np.sqrt(50), weight=10.0),
            RangeInput(
                ref_x=0, ref_y=10, ref_z=0, distance_m=np.sqrt(50) + 3.0, weight=0.1
            ),  # bad measurement
        ]

        pos = solver.solve(ranges)
        # Should be closer to the true position since the bad measurement has low weight
        error = np.sqrt((pos.x - target_x) ** 2 + (pos.y - target_y) ** 2)
        assert error < 3.0

    def test_insufficient_refs_raises(self):
        """Fewer than 2 reference points should raise ValueError."""
        solver = TrilaterationSolver(use_3d=False)
        ranges = [RangeInput(ref_x=0, ref_y=0, ref_z=0, distance_m=5.0)]
        with pytest.raises(ValueError):
            solver.solve(ranges)

    def test_3d_trilateration(self):
        """3D solver with 4 reference points."""
        solver = TrilaterationSolver(use_3d=True)

        target = (5.0, 5.0, 2.0)
        refs = [(0, 0, 0), (10, 0, 0), (0, 10, 0), (5, 5, 5)]
        ranges = []
        for rx, ry, rz in refs:
            d = np.sqrt((target[0] - rx) ** 2 + (target[1] - ry) ** 2 + (target[2] - rz) ** 2)
            ranges.append(RangeInput(ref_x=rx, ref_y=ry, ref_z=rz, distance_m=d))

        pos = solver.solve(ranges)
        assert abs(pos.x - target[0]) < 0.1
        assert abs(pos.y - target[1]) < 0.1
        assert abs(pos.z - target[2]) < 0.1

    def test_linearized_solver(self):
        """Fast linearized solver should give reasonable results."""
        target_x, target_y = 5.0, 5.0
        refs = [(0, 0), (10, 0), (0, 10)]
        ranges = []
        for rx, ry in refs:
            d = np.sqrt((target_x - rx) ** 2 + (target_y - ry) ** 2)
            ranges.append(RangeInput(ref_x=rx, ref_y=ry, ref_z=0, distance_m=d))

        pos = TrilaterationSolver.linearized_solve_2d(ranges)
        assert abs(pos.x - target_x) < 0.1
        assert abs(pos.y - target_y) < 0.1
