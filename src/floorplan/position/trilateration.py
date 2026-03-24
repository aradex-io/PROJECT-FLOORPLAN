"""Trilateration solver — compute position from multiple range measurements.

Uses Weighted Least Squares (WLS) minimization to find the position that best
fits the measured distances to known reference points.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from floorplan.models import Position

logger = logging.getLogger(__name__)


@dataclass
class RangeInput:
    """A single range measurement to a known reference point."""

    ref_x: float
    ref_y: float
    ref_z: float
    distance_m: float
    weight: float = 1.0  # inverse of measurement variance


class TrilaterationSolver:
    """Solves for 2D/3D position given multiple range measurements.

    Methods:
        solve_2d: Position from ranges to reference points (x, y only).
        solve_3d: Full 3D position including z-coordinate.
    """

    def __init__(self, use_3d: bool = False) -> None:
        self.use_3d = use_3d

    def solve(self, ranges: list[RangeInput]) -> Position:
        """Compute position from range measurements.

        Args:
            ranges: List of range measurements to known reference points.
                    Need ≥3 for 2D, ≥4 for 3D.

        Returns:
            Estimated position with uncertainty.

        Raises:
            ValueError: If insufficient reference points.
        """
        min_refs = 4 if self.use_3d else 3
        if len(ranges) < min_refs:
            if len(ranges) < 2:
                raise ValueError(
                    f"Need ≥{min_refs} reference points, got {len(ranges)}"
                )
            # Underdetermined: provide best estimate with high uncertainty
            logger.warning(
                "Underdetermined: %d refs (need %d) — position will have high uncertainty",
                len(ranges),
                min_refs,
            )

        if self.use_3d:
            return self._solve_3d(ranges)
        return self._solve_2d(ranges)

    def _solve_2d(self, ranges: list[RangeInput]) -> Position:
        """2D trilateration using Weighted Least Squares."""
        refs = np.array([[r.ref_x, r.ref_y] for r in ranges])
        dists = np.array([r.distance_m for r in ranges])
        weights = np.array([r.weight for r in ranges])

        # Initial guess: weighted centroid of reference points
        w_sum = weights.sum()
        x0 = np.array([
            np.sum(refs[:, 0] * weights) / w_sum,
            np.sum(refs[:, 1] * weights) / w_sum,
        ])

        def residuals(pos: np.ndarray) -> np.ndarray:
            computed_dists = np.sqrt(
                (refs[:, 0] - pos[0]) ** 2 + (refs[:, 1] - pos[1]) ** 2
            )
            return np.sqrt(weights) * (dists - computed_dists)

        result = least_squares(residuals, x0, method="lm")

        # Estimate uncertainty from residuals
        if result.fun.size > 0:
            rmse = float(np.sqrt(np.mean(result.fun**2)))
        else:
            rmse = float("inf")

        return Position(
            x=float(result.x[0]),
            y=float(result.x[1]),
            z=0.0,
            uncertainty_m=rmse,
        )

    def _solve_3d(self, ranges: list[RangeInput]) -> Position:
        """3D trilateration using Weighted Least Squares."""
        refs = np.array([[r.ref_x, r.ref_y, r.ref_z] for r in ranges])
        dists = np.array([r.distance_m for r in ranges])
        weights = np.array([r.weight for r in ranges])

        w_sum = weights.sum()
        x0 = np.array([
            np.sum(refs[:, 0] * weights) / w_sum,
            np.sum(refs[:, 1] * weights) / w_sum,
            np.sum(refs[:, 2] * weights) / w_sum,
        ])

        def residuals(pos: np.ndarray) -> np.ndarray:
            computed_dists = np.sqrt(
                (refs[:, 0] - pos[0]) ** 2
                + (refs[:, 1] - pos[1]) ** 2
                + (refs[:, 2] - pos[2]) ** 2
            )
            return np.sqrt(weights) * (dists - computed_dists)

        result = least_squares(residuals, x0, method="lm")

        rmse = float(np.sqrt(np.mean(result.fun**2))) if result.fun.size > 0 else float("inf")

        return Position(
            x=float(result.x[0]),
            y=float(result.x[1]),
            z=float(result.x[2]),
            uncertainty_m=rmse,
        )

    @staticmethod
    def linearized_solve_2d(ranges: list[RangeInput]) -> Position:
        """Fast linearized 2D solver (less accurate but no iteration).

        Uses the algebraic reduction: subtract the last equation from all others
        to get a linear system Ax = b.
        """
        if len(ranges) < 3:
            raise ValueError(f"Need ≥3 reference points, got {len(ranges)}")

        n = len(ranges)
        refs = np.array([[r.ref_x, r.ref_y] for r in ranges])
        dists = np.array([r.distance_m for r in ranges])

        # Use the last reference as the pivot
        x_n, y_n = refs[-1]
        d_n = dists[-1]

        # Build linear system: A @ [x, y] = b
        A = np.zeros((n - 1, 2))
        b = np.zeros(n - 1)

        for i in range(n - 1):
            x_i, y_i = refs[i]
            d_i = dists[i]
            A[i, 0] = 2 * (x_i - x_n)
            A[i, 1] = 2 * (y_i - y_n)
            b[i] = (
                d_n**2 - d_i**2 - x_n**2 + x_i**2 - y_n**2 + y_i**2
            )

        # Solve via least squares
        result, residuals_arr, _, _ = np.linalg.lstsq(A, b, rcond=None)

        uncertainty = 0.0
        if residuals_arr.size > 0:
            uncertainty = float(np.sqrt(residuals_arr[0] / (n - 1)))

        return Position(
            x=float(result[0]),
            y=float(result[1]),
            z=0.0,
            uncertainty_m=uncertainty,
        )
