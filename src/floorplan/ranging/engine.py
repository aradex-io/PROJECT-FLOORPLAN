"""High-level ranging engine that orchestrates FTM measurements."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from floorplan.models import BurstConfig, RangingMeasurement
from floorplan.ranging.calibration import CalibrationProfile, RangingCalibrator
from floorplan.ranging.nl80211 import NL80211Interface, FTMResult
from floorplan.ranging.nlos import NLOSDetector

logger = logging.getLogger(__name__)

# Speed of light in mm/ps (for RTT to distance conversion)
SPEED_OF_LIGHT_MM_PS = 0.000299792458


@dataclass
class RangingResult:
    """Processed ranging result with calibration and NLOS detection applied."""

    target_mac: str
    distance_m: float
    std_dev_m: float
    rssi_dbm: int
    rtt_ns: float
    timestamp: float
    raw_distance_m: float
    is_nlos: bool
    nlos_confidence: float
    num_successful: int
    num_attempted: int


class RangingEngine:
    """Manages FTM ranging to multiple targets with calibration and NLOS detection.

    The engine runs a background thread that cycles through a list of targets,
    performs FTM measurements, applies calibration corrections, and makes results
    available to consumers (e.g., the position engine).
    """

    def __init__(
        self,
        interface: str = "wlan0",
        burst_config: Optional[BurstConfig] = None,
        calibrator: Optional[RangingCalibrator] = None,
    ) -> None:
        self.interface = interface
        self.burst_config = burst_config or BurstConfig.fast()
        self.calibrator = calibrator or RangingCalibrator()
        self.nlos_detector = NLOSDetector()
        self._nl80211 = NL80211Interface(interface)

        # Target management
        self._targets: dict[str, int] = {}  # mac -> channel
        self._target_lock = threading.Lock()

        # Result buffers (thread-safe)
        self._results: dict[str, deque[RangingResult]] = {}
        self._results_lock = threading.Lock()
        self._max_history = 100

        # Continuous ranging
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable[[RangingResult], None]] = []

    def add_target(self, mac: str, channel: int) -> None:
        """Add a target device for ranging."""
        mac = mac.lower()
        with self._target_lock:
            self._targets[mac] = channel
        with self._results_lock:
            if mac not in self._results:
                self._results[mac] = deque(maxlen=self._max_history)
        logger.info("Added ranging target: %s on channel %d", mac, channel)

    def remove_target(self, mac: str) -> None:
        """Remove a target device from ranging."""
        mac = mac.lower()
        with self._target_lock:
            self._targets.pop(mac, None)
        logger.info("Removed ranging target: %s", mac)

    def on_result(self, callback: Callable[[RangingResult], None]) -> None:
        """Register a callback for new ranging results."""
        self._callbacks.append(callback)

    def range_once(self, mac: str, channel: int) -> Optional[RangingResult]:
        """Perform a single ranging measurement to a target."""
        mac = mac.lower()
        raw_results = self._nl80211.start_ftm_measurement(
            target_mac=mac,
            channel=channel,
            num_bursts_exp=_bursts_to_exp(self.burst_config.num_bursts),
            ftms_per_burst=self.burst_config.ftms_per_burst,
            burst_period_ms=self.burst_config.burst_period_ms,
        )

        if not raw_results:
            logger.warning("No FTM results from %s", mac)
            return None

        # Aggregate burst results
        return self._process_results(mac, raw_results)

    def get_latest(self, mac: str) -> Optional[RangingResult]:
        """Get the most recent ranging result for a target."""
        mac = mac.lower()
        with self._results_lock:
            buf = self._results.get(mac)
            if buf:
                return buf[-1]
        return None

    def get_history(self, mac: str, max_results: int = 0) -> list[RangingResult]:
        """Get ranging history for a target."""
        mac = mac.lower()
        with self._results_lock:
            buf = self._results.get(mac)
            if not buf:
                return []
            items = list(buf)
        if max_results > 0:
            items = items[-max_results:]
        return items

    def start_continuous(self, interval_s: float = 0.0) -> None:
        """Start continuous ranging in a background thread."""
        if self._running:
            return
        self._nl80211.connect()
        self._running = True
        self._thread = threading.Thread(
            target=self._ranging_loop,
            args=(interval_s,),
            daemon=True,
            name="floorplan-ranging",
        )
        self._thread.start()
        logger.info("Continuous ranging started (interval=%.2fs)", interval_s)

    def stop_continuous(self) -> None:
        """Stop continuous ranging."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._nl80211.close()
        logger.info("Continuous ranging stopped")

    def check_hardware(self) -> dict[str, bool]:
        """Check FTM hardware capabilities."""
        self._nl80211.connect()
        caps = self._nl80211.check_ftm_support()
        self._nl80211.close()
        return caps

    def _ranging_loop(self, interval_s: float) -> None:
        """Background loop that cycles through targets and measures."""
        while self._running:
            with self._target_lock:
                targets = list(self._targets.items())

            if not targets:
                time.sleep(0.1)
                continue

            for mac, channel in targets:
                if not self._running:
                    break
                result = self.range_once(mac, channel)
                if result:
                    with self._results_lock:
                        if mac not in self._results:
                            self._results[mac] = deque(maxlen=self._max_history)
                        self._results[mac].append(result)
                    for cb in self._callbacks:
                        try:
                            cb(result)
                        except Exception as e:
                            logger.error("Ranging callback error: %s", e)

            if interval_s > 0:
                time.sleep(interval_s)

    def _process_results(self, mac: str, raw_results: list[FTMResult]) -> RangingResult:
        """Aggregate and process raw FTM burst results."""
        # Filter out failed bursts
        valid = [r for r in raw_results if r.fail_reason is None]
        if not valid:
            valid = raw_results  # use what we have

        # Average distance across bursts
        distances_mm = [r.dist_avg_mm for r in valid]
        avg_dist_mm = sum(distances_mm) / len(distances_mm)
        raw_distance_m = avg_dist_mm / 1000.0

        # Standard deviation
        if len(distances_mm) > 1:
            variance = sum((d - avg_dist_mm) ** 2 for d in distances_mm) / (
                len(distances_mm) - 1
            )
            std_dev_m = (variance**0.5) / 1000.0
        else:
            std_dev_m = (valid[0].dist_variance_mm**0.5) / 1000.0 if valid else 1.0

        # Average RTT
        rtt_values = [r.rtt_avg_ps for r in valid]
        avg_rtt_ps = sum(rtt_values) / len(rtt_values)
        avg_rtt_ns = avg_rtt_ps / 1000.0

        # Average RSSI
        rssi_values = [r.rssi_avg_dbm for r in valid]
        avg_rssi = int(sum(rssi_values) / len(rssi_values))

        # NLOS detection
        rtt_variances = [r.rtt_variance_ps for r in valid]
        is_nlos, nlos_conf = self.nlos_detector.detect(
            distances_mm=distances_mm,
            rtt_variances=rtt_variances,
            rssi_dbm=avg_rssi,
        )

        # Apply calibration
        calibrated_distance_m = self.calibrator.correct(
            raw_distance_m, rssi_dbm=avg_rssi, is_nlos=is_nlos
        )

        total_attempts = sum(r.num_ftmr_attempts for r in raw_results)
        total_successes = sum(r.num_ftmr_successes for r in raw_results)

        return RangingResult(
            target_mac=mac,
            distance_m=calibrated_distance_m,
            std_dev_m=std_dev_m,
            rssi_dbm=avg_rssi,
            rtt_ns=avg_rtt_ns,
            timestamp=time.time(),
            raw_distance_m=raw_distance_m,
            is_nlos=is_nlos,
            nlos_confidence=nlos_conf,
            num_successful=total_successes,
            num_attempted=total_attempts,
        )

    def __enter__(self) -> RangingEngine:
        self._nl80211.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop_continuous()


def _bursts_to_exp(num_bursts: int) -> int:
    """Convert number of bursts to exponent (actual bursts = 2^exp)."""
    if num_bursts <= 1:
        return 0
    exp = 0
    while (1 << exp) < num_bursts:
        exp += 1
    return exp
