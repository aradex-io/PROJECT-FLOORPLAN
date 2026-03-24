"""Monitor mode management for passive Wi-Fi surveillance.

Handles putting a Wi-Fi interface into monitor mode, setting channels,
and cleaning up when done.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MonitorStatus:
    """Current state of a monitor-mode interface."""

    interface: str
    monitor_interface: str
    is_active: bool
    channel: int
    frequency_mhz: int


class MonitorMode:
    """Manages a Wi-Fi interface in monitor mode for passive frame capture."""

    def __init__(self, interface: str = "wlan0") -> None:
        self.interface = interface
        self.monitor_interface = f"{interface}mon"
        self._active = False
        self._channel = 0

    def enable(self, channel: int = 0) -> MonitorStatus:
        """Put the interface into monitor mode.

        Args:
            channel: Wi-Fi channel to listen on (0 = don't change).

        Returns:
            MonitorStatus with the active monitor interface details.
        """
        try:
            # Method 1: Use iw to create a separate monitor interface
            self._run_cmd(["ip", "link", "set", self.interface, "down"])
            self._run_cmd(["iw", self.interface, "set", "type", "monitor"])
            self._run_cmd(["ip", "link", "set", self.interface, "up"])
            self.monitor_interface = self.interface

            if channel > 0:
                self.set_channel(channel)

            self._active = True
            logger.info(
                "Monitor mode enabled on %s (channel %d)",
                self.monitor_interface,
                channel,
            )

        except subprocess.CalledProcessError as e:
            # Try alternative: airmon-ng style
            logger.warning("iw method failed (%s), trying alternative", e)
            try:
                result = self._run_cmd(
                    ["iw", "phy", f"phy{self._get_phy_index()}", "interface", "add",
                     self.monitor_interface, "type", "monitor"],
                    check=False,
                )
                self._run_cmd(["ip", "link", "set", self.monitor_interface, "up"])
                if channel > 0:
                    self.set_channel(channel)
                self._active = True
            except Exception as e2:
                logger.error("Failed to enable monitor mode: %s", e2)
                raise RuntimeError(f"Cannot enable monitor mode: {e2}") from e2

        return self.status()

    def disable(self) -> None:
        """Restore the interface to managed mode."""
        if not self._active:
            return

        try:
            self._run_cmd(["ip", "link", "set", self.monitor_interface, "down"])

            if self.monitor_interface != self.interface:
                self._run_cmd(
                    ["iw", self.monitor_interface, "del"], check=False
                )
            else:
                self._run_cmd(["iw", self.interface, "set", "type", "managed"])

            self._run_cmd(["ip", "link", "set", self.interface, "up"])
            self._active = False
            logger.info("Monitor mode disabled, restored %s to managed", self.interface)

        except Exception as e:
            logger.error("Error disabling monitor mode: %s", e)

    def set_channel(self, channel: int) -> None:
        """Switch the monitor interface to a specific channel."""
        freq = self._channel_to_freq(channel)
        iface = self.monitor_interface if self._active else self.interface
        try:
            self._run_cmd(["iw", "dev", iface, "set", "channel", str(channel)])
            self._channel = channel
            logger.debug("Set channel %d (%d MHz) on %s", channel, freq, iface)
        except subprocess.CalledProcessError:
            # Try setting by frequency
            self._run_cmd(["iw", "dev", iface, "set", "freq", str(freq)])
            self._channel = channel

    def status(self) -> MonitorStatus:
        """Get current monitor mode status."""
        return MonitorStatus(
            interface=self.interface,
            monitor_interface=self.monitor_interface,
            is_active=self._active,
            channel=self._channel,
            frequency_mhz=self._channel_to_freq(self._channel) if self._channel else 0,
        )

    def _get_phy_index(self) -> int:
        """Get the phy index for the interface."""
        try:
            with open(f"/sys/class/net/{self.interface}/phy80211/index") as f:
                return int(f.read().strip())
        except FileNotFoundError:
            return 0

    @staticmethod
    def _channel_to_freq(channel: int) -> int:
        """Convert Wi-Fi channel number to frequency in MHz."""
        if channel <= 0:
            return 0
        if channel <= 14:
            # 2.4 GHz band
            if channel == 14:
                return 2484
            return 2407 + channel * 5
        if channel <= 177:
            # 5 GHz band
            return 5000 + channel * 5
        # 6 GHz band (Wi-Fi 6E)
        return 5950 + channel * 5

    @staticmethod
    def _run_cmd(
        cmd: list[str], check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        logger.debug("Running: %s", " ".join(cmd))
        return subprocess.run(
            cmd, capture_output=True, text=True, check=check, timeout=10
        )

    def __enter__(self) -> MonitorMode:
        return self

    def __exit__(self, *args: object) -> None:
        self.disable()
