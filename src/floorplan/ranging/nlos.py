"""Non-Line-of-Sight (NLOS) detection for FTM measurements.

NLOS measurements are biased long because the signal travels through or around
obstacles. Detection uses RTT variance analysis and RSSI anomaly detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class NLOSThresholds:
    """Tunable thresholds for NLOS detection."""

    # RTT variance threshold — NLOS typically shows higher variance
    rtt_variance_threshold_ps: float = 5000.0
    # Coefficient of variation threshold for distance measurements
    distance_cv_threshold: float = 0.15
    # RSSI anomaly: if RSSI is much lower than expected for the measured distance
    rssi_path_loss_exponent: float = 2.5
    rssi_reference_dbm: float = -30.0  # RSSI at 1m reference
    rssi_anomaly_threshold_db: float = 10.0


class NLOSDetector:
    """Detects Non-Line-of-Sight conditions in FTM measurements."""

    def __init__(self, thresholds: NLOSThresholds | None = None) -> None:
        self.thresholds = thresholds or NLOSThresholds()

    def detect(
        self,
        distances_mm: list[int | float],
        rtt_variances: list[int | float],
        rssi_dbm: int,
    ) -> tuple[bool, float]:
        """Detect NLOS condition from measurement statistics.

        Returns:
            Tuple of (is_nlos, confidence) where confidence is 0.0-1.0.
        """
        scores: list[float] = []
        t = self.thresholds

        # Test 1: RTT variance analysis
        if rtt_variances:
            avg_variance = float(np.mean(rtt_variances))
            if avg_variance > t.rtt_variance_threshold_ps:
                ratio = min(avg_variance / t.rtt_variance_threshold_ps, 3.0)
                scores.append(min(ratio / 3.0, 1.0))
            else:
                scores.append(0.0)

        # Test 2: Distance coefficient of variation
        if len(distances_mm) >= 2:
            arr = np.array(distances_mm, dtype=float)
            mean_d = np.mean(arr)
            if mean_d > 0:
                cv = float(np.std(arr) / mean_d)
                if cv > t.distance_cv_threshold:
                    ratio = min(cv / t.distance_cv_threshold, 3.0)
                    scores.append(min(ratio / 3.0, 1.0))
                else:
                    scores.append(0.0)

        # Test 3: RSSI anomaly (path loss model comparison)
        if distances_mm and rssi_dbm < 0:
            avg_dist_m = float(np.mean(distances_mm)) / 1000.0
            if avg_dist_m > 0:
                # Expected RSSI from free-space path loss model
                expected_rssi = t.rssi_reference_dbm - (
                    10 * t.rssi_path_loss_exponent * np.log10(avg_dist_m)
                )
                rssi_delta = expected_rssi - rssi_dbm
                if rssi_delta > t.rssi_anomaly_threshold_db:
                    ratio = min(rssi_delta / (t.rssi_anomaly_threshold_db * 2), 1.0)
                    scores.append(ratio)
                else:
                    scores.append(0.0)

        if not scores:
            return False, 0.0

        # Weighted average of detection scores
        confidence = float(np.mean(scores))
        is_nlos = confidence > 0.4

        if is_nlos:
            logger.debug("NLOS detected (confidence=%.2f)", confidence)

        return is_nlos, confidence
