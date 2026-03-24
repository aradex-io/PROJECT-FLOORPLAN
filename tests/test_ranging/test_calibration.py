"""Tests for ranging calibration."""

import tempfile
from pathlib import Path

from floorplan.ranging.calibration import CalibrationProfile, RangingCalibrator


class TestCalibrationProfile:
    """Test single calibration profile."""

    def test_default_no_correction(self):
        """Default profile should not change measurements."""
        profile = CalibrationProfile(name="default")
        assert profile.correct(5.0) == 5.0
        assert profile.correct(10.0) == 10.0

    def test_linear_correction(self):
        """Profile with slope/intercept should apply linear correction."""
        profile = CalibrationProfile(name="test", slope=1.1, intercept=-0.5)
        corrected = profile.correct(5.0)
        assert abs(corrected - (1.1 * 5.0 - 0.5)) < 0.001

    def test_nlos_correction(self):
        """NLOS correction should subtract additional bias."""
        profile = CalibrationProfile(name="test", slope=1.0, intercept=0.0, nlos_bias_m=0.8)
        los = profile.correct(5.0, is_nlos=False)
        nlos = profile.correct(5.0, is_nlos=True)
        assert abs(los - 5.0) < 0.001
        assert abs(nlos - 4.2) < 0.001

    def test_negative_clamp(self):
        """Corrected distance should never go negative."""
        profile = CalibrationProfile(name="test", slope=1.0, intercept=-10.0)
        assert profile.correct(2.0) == 0.0

    def test_fit_from_measurements(self):
        """Fitting from measurement pairs should produce good correction."""
        profile = CalibrationProfile(name="test")
        # Simulated bias: measured = 1.1 * actual + 0.3
        for actual in [1.0, 3.0, 5.0, 8.0, 10.0]:
            measured = 1.1 * actual + 0.3
            profile.add_measurement(measured, actual)

        profile.fit()
        # After fitting, correction should be close to inverse of bias
        corrected = profile.correct(1.1 * 5.0 + 0.3)
        assert abs(corrected - 5.0) < 0.1


class TestRangingCalibrator:
    """Test multi-profile calibrator."""

    def test_add_and_use_profile(self):
        """Adding and activating a profile should apply corrections."""
        calibrator = RangingCalibrator()
        profile = CalibrationProfile(name="office", slope=0.95, intercept=0.1)
        calibrator.add_profile(profile)
        calibrator.set_active("office")

        corrected = calibrator.correct(5.0)
        assert abs(corrected - (0.95 * 5.0 + 0.1)) < 0.001

    def test_no_profile_passthrough(self):
        """Without active profile, distances should pass through unchanged."""
        calibrator = RangingCalibrator()
        assert calibrator.correct(5.0) == 5.0

    def test_save_and_load(self):
        """Profiles should survive save/load round-trip."""
        calibrator = RangingCalibrator()
        profile = CalibrationProfile(name="test", slope=1.05, intercept=-0.2)
        profile.add_measurement(5.0, 4.8)
        calibrator.add_profile(profile)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        calibrator.save(path)

        calibrator2 = RangingCalibrator()
        calibrator2.load(path)
        calibrator2.set_active("test")

        corrected = calibrator2.correct(5.0)
        assert abs(corrected - (1.05 * 5.0 - 0.2)) < 0.001

        path.unlink()
