"""Ranging calibration — bias correction and per-environment profiles."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CalibrationProfile:
    """Calibration profile for a specific environment type.

    Stores linear regression coefficients for bias correction:
        corrected = slope * measured + intercept
    """

    name: str
    slope: float = 1.0
    intercept: float = 0.0
    nlos_bias_m: float = 0.5  # additional bias correction for NLOS
    measurements: list[tuple[float, float]] = field(
        default_factory=list
    )  # (measured, actual) pairs

    def correct(self, measured_m: float, is_nlos: bool = False) -> float:
        """Apply calibration correction to a measured distance."""
        corrected = self.slope * measured_m + self.intercept
        if is_nlos:
            corrected -= self.nlos_bias_m
        return max(0.0, corrected)

    def fit(self) -> None:
        """Fit calibration coefficients from stored measurement pairs."""
        if len(self.measurements) < 2:
            logger.warning(
                "Profile '%s': need ≥2 measurements for calibration, got %d",
                self.name,
                len(self.measurements),
            )
            return

        measured = np.array([m[0] for m in self.measurements])
        actual = np.array([m[1] for m in self.measurements])

        # Linear regression: actual = slope * measured + intercept
        coeffs = np.polyfit(measured, actual, 1)
        self.slope = float(coeffs[0])
        self.intercept = float(coeffs[1])

        residuals = actual - (self.slope * measured + self.intercept)
        rmse = float(np.sqrt(np.mean(residuals**2)))
        logger.info(
            "Profile '%s' calibrated: slope=%.4f, intercept=%.4f, RMSE=%.3fm",
            self.name,
            self.slope,
            self.intercept,
            rmse,
        )

    def add_measurement(self, measured_m: float, actual_m: float) -> None:
        """Add a calibration measurement pair."""
        self.measurements.append((measured_m, actual_m))


class RangingCalibrator:
    """Manages multiple calibration profiles and applies corrections."""

    def __init__(self) -> None:
        self._profiles: dict[str, CalibrationProfile] = {}
        self._active_profile: CalibrationProfile | None = None

    def add_profile(self, profile: CalibrationProfile) -> None:
        """Register a calibration profile."""
        self._profiles[profile.name] = profile

    def set_active(self, name: str) -> None:
        """Set the active calibration profile by name."""
        if name not in self._profiles:
            raise KeyError(f"Unknown calibration profile: {name}")
        self._active_profile = self._profiles[name]
        logger.info("Active calibration profile: %s", name)

    def correct(
        self,
        distance_m: float,
        *,
        rssi_dbm: int = 0,
        is_nlos: bool = False,
        profile_name: str | None = None,
    ) -> float:
        """Apply calibration correction to a distance measurement."""
        profile = self._active_profile
        if profile_name:
            profile = self._profiles.get(profile_name)

        if profile:
            return profile.correct(distance_m, is_nlos=is_nlos)
        return distance_m

    def save(self, path: str | Path) -> None:
        """Save all calibration profiles to a JSON file."""
        path = Path(path)
        data = {}
        for name, profile in self._profiles.items():
            data[name] = {
                "slope": profile.slope,
                "intercept": profile.intercept,
                "nlos_bias_m": profile.nlos_bias_m,
                "measurements": profile.measurements,
            }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved %d calibration profiles to %s", len(data), path)

    def load(self, path: str | Path) -> None:
        """Load calibration profiles from a JSON file."""
        path = Path(path)
        with open(path) as f:
            data = json.load(f)

        for name, pdata in data.items():
            profile = CalibrationProfile(
                name=name,
                slope=pdata.get("slope", 1.0),
                intercept=pdata.get("intercept", 0.0),
                nlos_bias_m=pdata.get("nlos_bias_m", 0.5),
                measurements=[tuple(m) for m in pdata.get("measurements", [])],
            )
            self._profiles[name] = profile

        logger.info("Loaded %d calibration profiles from %s", len(data), path)
