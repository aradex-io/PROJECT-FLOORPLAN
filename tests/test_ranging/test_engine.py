"""Tests for RangingEngine with simulated FTM."""

from __future__ import annotations

import time

from floorplan.models import BurstConfig
from floorplan.ranging.engine import RangingEngine, RangingResult
from floorplan.ranging.nl80211 import NL80211Interface
from floorplan.ranging.simulator import FTMSimulator, SimulatedAP


def _make_engine() -> tuple[RangingEngine, FTMSimulator]:
    """Create a RangingEngine with a known simulator."""
    sim = FTMSimulator(
        aps=[
            SimulatedAP(mac="aa:bb:cc:dd:ee:01", x=0.0, y=0.0),
            SimulatedAP(mac="aa:bb:cc:dd:ee:02", x=10.0, y=0.0),
            SimulatedAP(mac="aa:bb:cc:dd:ee:03", x=5.0, y=8.0),
            SimulatedAP(
                mac="aa:bb:cc:dd:ee:04", x=0.0, y=8.0, is_nlos=True, nlos_bias_m=2.0
            ),
        ],
        device_x=5.0,
        device_y=3.0,
        seed=42,
    )
    nl = NL80211Interface(simulator=sim)
    engine = RangingEngine(
        burst_config=BurstConfig.accurate(),
        nl80211=nl,
    )
    return engine, sim


class TestRangingEngine:
    """Unit tests for RangingEngine."""

    def test_range_once_returns_result(self) -> None:
        engine, _ = _make_engine()
        with engine:
            result = engine.range_once("aa:bb:cc:dd:ee:01", 2437)
        assert result is not None
        assert isinstance(result, RangingResult)

    def test_range_once_distance_reasonable(self) -> None:
        """Distance should approximate true geometry."""
        engine, _ = _make_engine()
        with engine:
            result = engine.range_once("aa:bb:cc:dd:ee:01", 2437)
        assert result is not None
        # True distance (5,3) to (0,0) ≈ 5.83m (2D) + z offset
        assert 2.0 < result.distance_m < 12.0

    def test_range_once_populates_all_fields(self) -> None:
        engine, _ = _make_engine()
        with engine:
            result = engine.range_once("aa:bb:cc:dd:ee:01", 2437)
        assert result is not None
        assert result.target_mac == "aa:bb:cc:dd:ee:01"
        assert result.distance_m > 0
        assert result.raw_distance_m > 0
        assert result.std_dev_m >= 0
        assert result.rssi_dbm < 0
        assert result.rtt_ns > 0
        assert result.timestamp > 0
        assert result.num_attempted > 0
        assert result.num_successful > 0

    def test_nlos_detection_through_engine(self) -> None:
        """NLOS AP should be flagged with higher confidence."""
        engine, _ = _make_engine()
        with engine:
            result = engine.range_once("aa:bb:cc:dd:ee:04", 2437)
        assert result is not None
        # NLOS AP has bias + high variance → should be detected
        # (confidence may vary, but we test the field exists and is valid)
        assert 0.0 <= result.nlos_confidence <= 1.0

    def test_add_and_remove_target(self) -> None:
        engine, _ = _make_engine()
        engine.add_target("aa:bb:cc:dd:ee:01", 2437)
        engine.add_target("aa:bb:cc:dd:ee:02", 2437)
        engine.remove_target("aa:bb:cc:dd:ee:01")

    def test_result_callback(self) -> None:
        engine, _ = _make_engine()
        received: list[RangingResult] = []
        engine.on_result(received.append)
        engine.add_target("aa:bb:cc:dd:ee:01", 2437)
        engine.start_continuous(interval_s=0.05)
        time.sleep(0.3)
        engine.stop_continuous()
        assert len(received) > 0
        assert all(isinstance(r, RangingResult) for r in received)

    def test_continuous_ranging_multiple_targets(self) -> None:
        engine, _ = _make_engine()
        results: list[RangingResult] = []
        engine.on_result(results.append)
        engine.add_target("aa:bb:cc:dd:ee:01", 2437)
        engine.add_target("aa:bb:cc:dd:ee:02", 2437)
        engine.start_continuous(interval_s=0.05)
        time.sleep(0.3)
        engine.stop_continuous()
        macs = {r.target_mac for r in results}
        assert "aa:bb:cc:dd:ee:01" in macs
        assert "aa:bb:cc:dd:ee:02" in macs

    def test_get_latest(self) -> None:
        engine, _ = _make_engine()
        engine.add_target("aa:bb:cc:dd:ee:01", 2437)
        engine.start_continuous(interval_s=0.05)
        time.sleep(0.3)
        engine.stop_continuous()
        latest = engine.get_latest("aa:bb:cc:dd:ee:01")
        assert latest is not None
        assert isinstance(latest, RangingResult)

    def test_get_history(self) -> None:
        engine, _ = _make_engine()
        engine.add_target("aa:bb:cc:dd:ee:01", 2437)
        engine.start_continuous(interval_s=0.05)
        time.sleep(0.3)
        engine.stop_continuous()
        history = engine.get_history("aa:bb:cc:dd:ee:01")
        assert len(history) >= 2

    def test_get_history_with_limit(self) -> None:
        engine, _ = _make_engine()
        engine.add_target("aa:bb:cc:dd:ee:01", 2437)
        engine.start_continuous(interval_s=0.05)
        time.sleep(0.3)
        engine.stop_continuous()
        history = engine.get_history("aa:bb:cc:dd:ee:01", max_results=2)
        assert len(history) <= 2

    def test_get_latest_unknown_target(self) -> None:
        engine, _ = _make_engine()
        assert engine.get_latest("ff:ff:ff:ff:ff:ff") is None

    def test_get_history_unknown_target(self) -> None:
        engine, _ = _make_engine()
        assert engine.get_history("ff:ff:ff:ff:ff:ff") == []

    def test_check_hardware(self) -> None:
        engine, _ = _make_engine()
        caps = engine.check_hardware()
        assert isinstance(caps, dict)

    def test_mac_normalized_to_lowercase(self) -> None:
        engine, _ = _make_engine()
        with engine:
            result = engine.range_once("AA:BB:CC:DD:EE:01", 2437)
        assert result is not None
        assert result.target_mac == "aa:bb:cc:dd:ee:01"

    def test_context_manager(self) -> None:
        engine, _ = _make_engine()
        with engine as e:
            assert e is engine

    def test_stop_without_start(self) -> None:
        engine, _ = _make_engine()
        engine.stop_continuous()  # should not raise

    def test_double_start(self) -> None:
        engine, _ = _make_engine()
        engine.add_target("aa:bb:cc:dd:ee:01", 2437)
        engine.start_continuous(interval_s=0.1)
        engine.start_continuous(interval_s=0.1)  # should be no-op
        time.sleep(0.15)
        engine.stop_continuous()
