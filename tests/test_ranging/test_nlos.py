"""Tests for NLOS detection."""

from floorplan.ranging.nlos import NLOSDetector, NLOSThresholds


class TestNLOSDetector:
    """Test NLOS detection heuristics."""

    def test_los_low_variance(self):
        """LOS measurements with low variance should not be flagged."""
        detector = NLOSDetector()
        is_nlos, confidence = detector.detect(
            distances_mm=[5000, 5050, 4980, 5020, 5010],
            rtt_variances=[100, 120, 90, 110, 105],
            rssi_dbm=-50,
        )
        assert not is_nlos
        assert confidence < 0.4

    def test_nlos_high_variance(self):
        """NLOS measurements with high RTT variance should be detected."""
        detector = NLOSDetector()
        is_nlos, confidence = detector.detect(
            distances_mm=[5000, 6500, 4200, 7000, 3800],
            rtt_variances=[10000, 12000, 15000, 11000, 13000],
            rssi_dbm=-75,
        )
        assert is_nlos
        assert confidence > 0.4

    def test_rssi_anomaly(self):
        """Very weak RSSI for short distance indicates NLOS."""
        detector = NLOSDetector()
        is_nlos, confidence = detector.detect(
            distances_mm=[2000, 2100, 1900],  # ~2m
            rtt_variances=[200, 250, 180],
            rssi_dbm=-80,  # Way too weak for 2m (should be ~-36dBm)
        )
        # RSSI anomaly should push confidence up
        assert confidence > 0.2

    def test_empty_input(self):
        """Empty input should return no NLOS."""
        detector = NLOSDetector()
        is_nlos, confidence = detector.detect(
            distances_mm=[],
            rtt_variances=[],
            rssi_dbm=0,
        )
        assert not is_nlos
        assert confidence == 0.0

    def test_custom_thresholds(self):
        """Custom thresholds should be respected."""
        detector = NLOSDetector(
            thresholds=NLOSThresholds(rtt_variance_threshold_ps=100.0)
        )
        # Even moderate variance should trigger with low threshold
        is_nlos, confidence = detector.detect(
            distances_mm=[5000, 5100, 4900],
            rtt_variances=[500, 600, 400],
            rssi_dbm=-50,
        )
        assert confidence > 0.3
