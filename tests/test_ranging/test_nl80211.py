"""Tests for NL80211Interface in simulation mode."""

from __future__ import annotations

from floorplan.ranging.nl80211 import NL80211Interface
from floorplan.ranging.simulator import FTMSimulator, SimulatedAP


def _make_simulator() -> FTMSimulator:
    """Create a simulator with a known 3-AP layout."""
    return FTMSimulator(
        aps=[
            SimulatedAP(mac="aa:bb:cc:dd:ee:01", x=0.0, y=0.0, channel=2437),
            SimulatedAP(mac="aa:bb:cc:dd:ee:02", x=10.0, y=0.0, channel=2437),
            SimulatedAP(mac="aa:bb:cc:dd:ee:03", x=5.0, y=8.0, channel=2437),
        ],
        device_x=5.0,
        device_y=3.0,
        seed=42,
    )


class TestNL80211Simulation:
    """Tests for NL80211Interface with injected FTMSimulator."""

    def test_connect_close_with_simulator(self) -> None:
        sim = _make_simulator()
        nl = NL80211Interface(simulator=sim)
        nl.connect()
        nl.close()

    def test_ftm_support_with_simulator(self) -> None:
        sim = _make_simulator()
        nl = NL80211Interface(simulator=sim)
        nl.connect()
        caps = nl.check_ftm_support()
        # Without real hardware, sysfs lookup fails → both remain False
        # This is expected behavior — FTM support check requires real phy
        assert isinstance(caps, dict)
        assert "ftm_initiator" in caps
        assert "ftm_responder" in caps
        nl.close()

    def test_measurement_returns_ftm_results(self) -> None:
        sim = _make_simulator()
        nl = NL80211Interface(simulator=sim)
        results = nl.start_ftm_measurement("aa:bb:cc:dd:ee:01", channel=2437)
        assert results is not None
        assert len(results) > 0

    def test_measurement_burst_count(self) -> None:
        sim = _make_simulator()
        nl = NL80211Interface(simulator=sim)
        # 2^2 = 4 bursts
        results = nl.start_ftm_measurement(
            "aa:bb:cc:dd:ee:01", channel=2437, num_bursts_exp=2
        )
        assert results is not None
        assert len(results) == 4

    def test_measurement_burst_count_higher(self) -> None:
        sim = _make_simulator()
        nl = NL80211Interface(simulator=sim)
        # 2^3 = 8 bursts
        results = nl.start_ftm_measurement(
            "aa:bb:cc:dd:ee:01", channel=2437, num_bursts_exp=3
        )
        assert results is not None
        assert len(results) == 8

    def test_result_fields_populated(self) -> None:
        sim = _make_simulator()
        nl = NL80211Interface(simulator=sim)
        results = nl.start_ftm_measurement("aa:bb:cc:dd:ee:02", channel=2437)
        assert results is not None
        r = results[0]
        assert r.target_mac == "aa:bb:cc:dd:ee:02"
        assert r.dist_avg_mm > 0
        assert r.rtt_avg_ps > 0
        assert r.rssi_avg_dbm < 0
        assert r.num_ftmr_attempts > 0
        assert r.num_ftmr_successes > 0
        assert r.fail_reason is None

    def test_distance_reflects_geometry(self) -> None:
        """Measured distance should approximate true geometric distance."""
        sim = _make_simulator()
        nl = NL80211Interface(simulator=sim)
        # True distance from (5,3) to (0,0) ≈ 5.93m
        results = nl.start_ftm_measurement(
            "aa:bb:cc:dd:ee:01", channel=2437, num_bursts_exp=3
        )
        assert results is not None
        avg_dist_m = sum(r.dist_avg_mm for r in results) / len(results) / 1000.0
        assert abs(avg_dist_m - 5.93) < 2.0  # within 2m tolerance

    def test_context_manager(self) -> None:
        sim = _make_simulator()
        with NL80211Interface(simulator=sim) as nl:
            results = nl.start_ftm_measurement("aa:bb:cc:dd:ee:01", channel=2437)
            assert results is not None

    def test_invalid_mac_raises(self) -> None:
        sim = _make_simulator()
        nl = NL80211Interface(simulator=sim)
        import pytest

        with pytest.raises(ValueError):
            nl.start_ftm_measurement("not-a-mac", channel=2437)

    def test_fallback_simulation_without_simulator(self) -> None:
        """Without simulator or pyroute2, falls back to random simulation."""
        nl = NL80211Interface()
        nl.connect()  # pyroute2 not available → _nl_socket stays None
        results = nl.start_ftm_measurement("aa:bb:cc:dd:ee:01", channel=2437)
        assert results is not None
        assert len(results) > 0
        nl.close()
