"""Tests for the track manager."""

from floorplan.config.models import ZoneConfig
from floorplan.models import Position, ZoneEvent
from floorplan.tracking.manager import TrackManager


class TestTrackManager:
    """Test multi-target tracking and zone alerting."""

    def test_new_device_creation(self):
        """First position update should create a new device."""
        manager = TrackManager()
        device = manager.update_position(
            "aa:bb:cc:dd:ee:ff",
            Position(5.0, 5.0),
            timestamp=1000.0,
        )
        assert device.device_id == "aa:bb:cc:dd:ee:ff"
        assert device.position.x == 5.0

    def test_device_update(self):
        """Subsequent updates should update existing device."""
        manager = TrackManager()
        manager.update_position("aa:bb:cc:dd:ee:ff", Position(5.0, 5.0), timestamp=1000.0)
        device = manager.update_position("aa:bb:cc:dd:ee:ff", Position(6.0, 5.0), timestamp=1001.0)
        assert device.position.x == 6.0
        assert device.measurement_count == 2

    def test_multiple_devices(self):
        """Should track multiple devices independently."""
        manager = TrackManager()
        manager.update_position("aa:bb:cc:00:00:01", Position(1.0, 1.0), timestamp=1000.0)
        manager.update_position("aa:bb:cc:00:00:02", Position(9.0, 9.0), timestamp=1000.0)

        devices = manager.get_all_devices()
        assert len(devices) == 2

    def test_zone_enter_alert(self):
        """Entering a zone should trigger an event."""
        zone = ZoneConfig(
            name="restricted",
            zone_type="restricted",
            vertices=[(0, 0), (5, 0), (5, 5), (0, 5)],
            alert_on_enter=True,
        )
        events: list[ZoneEvent] = []
        manager = TrackManager(zones=[zone])
        manager.on_zone_event(events.append)

        # First position outside zone
        manager.update_position("aa:bb:cc:dd:ee:ff", Position(8.0, 8.0), timestamp=1000.0)
        assert len(events) == 0

        # Move inside zone
        manager.update_position("aa:bb:cc:dd:ee:ff", Position(2.0, 2.0), timestamp=1001.0)
        assert len(events) == 1
        assert events[0].event_type == "enter"
        assert events[0].zone_name == "restricted"

    def test_zone_exit_alert(self):
        """Exiting a zone should trigger an event."""
        zone = ZoneConfig(
            name="office",
            zone_type="authorized",
            vertices=[(0, 0), (10, 0), (10, 10), (0, 10)],
            alert_on_exit=True,
        )
        events: list[ZoneEvent] = []
        manager = TrackManager(zones=[zone])
        manager.on_zone_event(events.append)

        # Start inside
        manager.update_position("aa:bb:cc:dd:ee:ff", Position(5.0, 5.0), timestamp=1000.0)
        # Move outside
        manager.update_position("aa:bb:cc:dd:ee:ff", Position(15.0, 15.0), timestamp=1001.0)
        assert len(events) == 1
        assert events[0].event_type == "exit"

    def test_point_in_polygon(self):
        """Point-in-polygon should work for various shapes."""
        # Square
        assert TrackManager._point_in_polygon(5, 5, [(0, 0), (10, 0), (10, 10), (0, 10)])
        assert not TrackManager._point_in_polygon(15, 5, [(0, 0), (10, 0), (10, 10), (0, 10)])
        # Triangle
        assert TrackManager._point_in_polygon(2, 1, [(0, 0), (5, 0), (2.5, 5)])
        assert not TrackManager._point_in_polygon(0, 5, [(0, 0), (5, 0), (2.5, 5)])

    def test_device_by_mac(self):
        """Should be able to look up device by MAC."""
        manager = TrackManager()
        manager.update_position("aa:bb:cc:dd:ee:ff", Position(5.0, 5.0), timestamp=1000.0)

        device = manager.get_device_by_mac("aa:bb:cc:dd:ee:ff")
        assert device is not None
        assert device.position.x == 5.0

    def test_remove_device(self):
        """Removing a device should clear it from tracking."""
        manager = TrackManager()
        manager.update_position("aa:bb:cc:dd:ee:ff", Position(5.0, 5.0), timestamp=1000.0)
        manager.remove_device("aa:bb:cc:dd:ee:ff")

        assert manager.get_device("aa:bb:cc:dd:ee:ff") is None
        assert len(manager.get_all_devices()) == 0
