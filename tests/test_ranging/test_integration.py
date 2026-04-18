"""Integration tests: simulator → RangingEngine → PositionEngine → Position.

Verifies the full ranging-to-position pipeline converges to the correct
device position using simulated FTM measurements.
"""

from __future__ import annotations

from floorplan.config.models import ReferencePoint
from floorplan.models import BurstConfig
from floorplan.position.engine import PositionEngine
from floorplan.ranging.engine import RangingEngine
from floorplan.ranging.nl80211 import NL80211Interface
from floorplan.ranging.simulator import FTMSimulator, SimulatedAP


def _office_layout() -> tuple[FTMSimulator, list[ReferencePoint]]:
    """Create a realistic office layout with 4 corner APs."""
    aps = [
        SimulatedAP(mac="aa:bb:cc:dd:ee:01", x=0.0, y=0.0, noise_std_m=0.2),
        SimulatedAP(mac="aa:bb:cc:dd:ee:02", x=10.0, y=0.0, noise_std_m=0.2),
        SimulatedAP(mac="aa:bb:cc:dd:ee:03", x=10.0, y=8.0, noise_std_m=0.2),
        SimulatedAP(mac="aa:bb:cc:dd:ee:04", x=0.0, y=8.0, noise_std_m=0.2),
    ]
    refs = [
        ReferencePoint(mac=ap.mac, channel=ap.channel, x=ap.x, y=ap.y, z=ap.z)
        for ap in aps
    ]
    sim = FTMSimulator(aps=aps, device_x=5.0, device_y=3.0, seed=123)
    return sim, refs


class TestRangingPositionIntegration:
    """End-to-end tests for the ranging → position pipeline."""

    def test_converges_with_4_aps(self) -> None:
        """Device at (5, 3) should converge within 2m with 4 LOS APs."""
        sim, refs = _office_layout()
        nl = NL80211Interface(simulator=sim)
        engine = RangingEngine(burst_config=BurstConfig.accurate(), nl80211=nl)
        pos_engine = PositionEngine(reference_points=refs, filter_type="kalman")

        with engine:
            for ref in refs:
                result = engine.range_once(ref.mac, ref.channel)
                assert result is not None
                pos_engine.add_measurement(
                    device_id="test-device",
                    ref_mac=result.target_mac,
                    distance_m=result.distance_m,
                    std_dev_m=result.std_dev_m,
                    timestamp=result.timestamp,
                )

        pos = pos_engine.get_position("test-device")
        assert pos is not None
        error = ((pos.x - 5.0) ** 2 + (pos.y - 3.0) ** 2) ** 0.5
        assert error < 2.0, f"Position error {error:.2f}m exceeds 2m threshold"

    def test_converges_with_3_aps(self) -> None:
        """Device should converge with minimum 3 APs."""
        sim, refs = _office_layout()
        refs_3 = refs[:3]  # Use only first 3 APs
        nl = NL80211Interface(simulator=sim)
        engine = RangingEngine(burst_config=BurstConfig.accurate(), nl80211=nl)
        pos_engine = PositionEngine(reference_points=refs_3, filter_type="kalman")

        with engine:
            for ref in refs_3:
                result = engine.range_once(ref.mac, ref.channel)
                assert result is not None
                pos_engine.add_measurement(
                    device_id="test-device",
                    ref_mac=result.target_mac,
                    distance_m=result.distance_m,
                    std_dev_m=result.std_dev_m,
                    timestamp=result.timestamp,
                )

        pos = pos_engine.get_position("test-device")
        assert pos is not None
        error = ((pos.x - 5.0) ** 2 + (pos.y - 3.0) ** 2) ** 0.5
        assert error < 3.0, f"Position error {error:.2f}m exceeds 3m threshold (3 APs)"

    def test_nlos_ap_degrades_but_converges(self) -> None:
        """One NLOS AP should degrade accuracy but still produce a valid position."""
        aps = [
            SimulatedAP(mac="aa:bb:cc:dd:ee:01", x=0.0, y=0.0, noise_std_m=0.2),
            SimulatedAP(mac="aa:bb:cc:dd:ee:02", x=10.0, y=0.0, noise_std_m=0.2),
            SimulatedAP(mac="aa:bb:cc:dd:ee:03", x=10.0, y=8.0, noise_std_m=0.2),
            SimulatedAP(
                mac="aa:bb:cc:dd:ee:04", x=0.0, y=8.0,
                is_nlos=True, nlos_bias_m=2.0, noise_std_m=0.5,
            ),
        ]
        refs = [
            ReferencePoint(mac=ap.mac, channel=ap.channel, x=ap.x, y=ap.y, z=ap.z)
            for ap in aps
        ]
        sim = FTMSimulator(aps=aps, device_x=5.0, device_y=3.0, seed=456)
        nl = NL80211Interface(simulator=sim)
        engine = RangingEngine(burst_config=BurstConfig.accurate(), nl80211=nl)
        pos_engine = PositionEngine(reference_points=refs, filter_type="kalman")

        with engine:
            for ref in refs:
                result = engine.range_once(ref.mac, ref.channel)
                assert result is not None
                pos_engine.add_measurement(
                    device_id="test-device",
                    ref_mac=result.target_mac,
                    distance_m=result.distance_m,
                    std_dev_m=result.std_dev_m,
                    timestamp=result.timestamp,
                )

        pos = pos_engine.get_position("test-device")
        assert pos is not None
        error = ((pos.x - 5.0) ** 2 + (pos.y - 3.0) ** 2) ** 0.5
        # Looser threshold since one AP is NLOS
        assert error < 4.0, f"Position error {error:.2f}m exceeds 4m threshold (1 NLOS AP)"

    def test_multiple_rounds_improve_accuracy(self) -> None:
        """Multiple ranging rounds should improve position estimate via Kalman."""
        sim, refs = _office_layout()
        nl = NL80211Interface(simulator=sim)
        engine = RangingEngine(burst_config=BurstConfig.accurate(), nl80211=nl)
        pos_engine = PositionEngine(reference_points=refs, filter_type="kalman")

        errors: list[float] = []
        with engine:
            for _round in range(5):
                for ref in refs:
                    result = engine.range_once(ref.mac, ref.channel)
                    assert result is not None
                    pos_engine.add_measurement(
                        device_id="test-device",
                        ref_mac=result.target_mac,
                        distance_m=result.distance_m,
                        std_dev_m=result.std_dev_m,
                        timestamp=result.timestamp,
                    )
                pos = pos_engine.get_position("test-device")
                assert pos is not None
                error = ((pos.x - 5.0) ** 2 + (pos.y - 3.0) ** 2) ** 0.5
                errors.append(error)

        # Final error should be less than or equal to first error
        assert errors[-1] <= errors[0] + 0.5  # allow small tolerance

    def test_particle_filter_integration(self) -> None:
        """Verify integration works with particle filter too."""
        sim, refs = _office_layout()
        nl = NL80211Interface(simulator=sim)
        engine = RangingEngine(burst_config=BurstConfig.accurate(), nl80211=nl)
        pos_engine = PositionEngine(reference_points=refs, filter_type="particle")

        with engine:
            for _round in range(3):
                for ref in refs:
                    result = engine.range_once(ref.mac, ref.channel)
                    assert result is not None
                    pos_engine.add_measurement(
                        device_id="test-device",
                        ref_mac=result.target_mac,
                        distance_m=result.distance_m,
                        std_dev_m=result.std_dev_m,
                        timestamp=result.timestamp,
                    )

        pos = pos_engine.get_position("test-device")
        assert pos is not None
        error = ((pos.x - 5.0) ** 2 + (pos.y - 3.0) ** 2) ** 0.5
        assert error < 4.0, f"Particle filter error {error:.2f}m exceeds 4m threshold"
