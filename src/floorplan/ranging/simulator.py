"""Configurable FTM simulator for hardware-free development and testing.

Generates realistic FTMResult objects from geometric AP layouts, with
controllable noise, NLOS bias, and deterministic seeding for reproducible tests.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from floorplan.ranging.nl80211 import FTMResult


@dataclass
class SimulatedAP:
    """A simulated FTM responder (access point) with known position."""

    mac: str
    x: float
    y: float
    z: float = 2.5
    channel: int = 2437
    is_nlos: bool = False
    nlos_bias_m: float = 1.5
    noise_std_m: float = 0.3
    rssi_at_1m: float = -30.0
    path_loss_exp: float = 2.5


@dataclass
class FTMSimulator:
    """Generates FTM results based on geometric distance to simulated APs.

    Usage:
        sim = FTMSimulator(aps=[...], device_x=5.0, device_y=3.0)
        results = sim.measure("aa:bb:cc:dd:ee:01", num_bursts_exp=2, ftms_per_burst=8)
    """

    aps: list[SimulatedAP] = field(default_factory=list)
    device_x: float = 0.0
    device_y: float = 0.0
    device_z: float = 1.0
    seed: int | None = None

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._ap_index: dict[str, SimulatedAP] = {ap.mac.lower(): ap for ap in self.aps}

    def add_ap(self, ap: SimulatedAP) -> None:
        """Register a simulated access point."""
        self.aps.append(ap)
        self._ap_index[ap.mac.lower()] = ap

    def set_device_position(self, x: float, y: float, z: float = 1.0) -> None:
        """Move the simulated device."""
        self.device_x = x
        self.device_y = y
        self.device_z = z

    def true_distance(self, mac: str) -> float:
        """Compute the true geometric distance to an AP in meters."""
        ap = self._ap_index.get(mac.lower())
        if ap is None:
            raise ValueError(f"Unknown AP: {mac}")
        dx = self.device_x - ap.x
        dy = self.device_y - ap.y
        dz = self.device_z - ap.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def measure(
        self,
        target_mac: str,
        num_bursts_exp: int = 2,
        ftms_per_burst: int = 8,
    ) -> list[FTMResult]:
        """Generate simulated FTM burst results for a target AP.

        Returns one FTMResult per burst, with noise and optional NLOS bias applied.
        """
        mac = target_mac.lower()
        ap = self._ap_index.get(mac)
        if ap is None:
            raise ValueError(f"Unknown AP: {target_mac}")

        true_dist_m = self.true_distance(mac)
        num_bursts = 2**num_bursts_exp
        results: list[FTMResult] = []

        for burst_idx in range(num_bursts):
            # Distance with Gaussian noise + optional NLOS bias
            noise_m = self._rng.gauss(0, ap.noise_std_m)
            nlos_extra = ap.nlos_bias_m if ap.is_nlos else 0.0
            measured_m = max(0.0, true_dist_m + noise_m + nlos_extra)
            dist_mm = int(measured_m * 1000)

            # RTT from distance: rtt = 2 * distance / c (in picoseconds)
            # c = 299792458 m/s = 0.000299792458 m/ps
            rtt_ps = int(measured_m * 2 / 0.000299792458)

            # Variance scales with noise and NLOS
            variance_factor = 3.0 if ap.is_nlos else 1.0
            rtt_var_ps = abs(int(self._rng.gauss(0, 1000 * variance_factor)))
            dist_var_mm = abs(int(self._rng.gauss(0, ap.noise_std_m * 1000 * variance_factor)))

            # RSSI from free-space path loss: RSSI = rssi_1m - 10*n*log10(d)
            if true_dist_m > 0.1:
                rssi = int(ap.rssi_at_1m - 10 * ap.path_loss_exp * math.log10(true_dist_m))
            else:
                rssi = int(ap.rssi_at_1m)
            # Add small RSSI noise
            rssi += self._rng.randint(-2, 2)
            # NLOS further degrades RSSI
            if ap.is_nlos:
                rssi -= self._rng.randint(5, 15)

            successes = max(1, ftms_per_burst - self._rng.randint(0, 1))

            results.append(
                FTMResult(
                    target_mac=mac,
                    rtt_avg_ps=rtt_ps,
                    rtt_variance_ps=rtt_var_ps,
                    rtt_spread_ps=abs(int(self._rng.gauss(0, 500 * variance_factor))),
                    dist_avg_mm=dist_mm,
                    dist_variance_mm=dist_var_mm,
                    dist_spread_mm=abs(int(self._rng.gauss(0, 200 * variance_factor))),
                    rssi_avg_dbm=rssi,
                    rssi_spread_dbm=self._rng.randint(1, 3),
                    burst_index=burst_idx,
                    num_ftmr_attempts=ftms_per_burst,
                    num_ftmr_successes=successes,
                )
            )

        return results
