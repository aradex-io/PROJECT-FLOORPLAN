"""Probe request monitoring — track devices via standard Wi-Fi probes.

Probe requests are broadcast management frames sent by devices searching for
networks. They reveal device presence and provide coarse RSSI-based positioning.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProbeSighting:
    """A single probe request observation."""

    mac: str
    ssid: Optional[str]
    rssi_dbm: int
    channel: int
    timestamp: float
    is_randomized_mac: bool


@dataclass
class ProbeDevice:
    """Aggregated probe request data for a device."""

    mac: str
    sighting_count: int = 0
    ssids_probed: set[str] = field(default_factory=set)
    channels_seen: set[int] = field(default_factory=set)
    rssi_history: list[tuple[float, int]] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    is_randomized_mac: bool = False


class ProbeTracker:
    """Tracks devices via probe request monitoring in monitor mode."""

    def __init__(self, interface: str = "wlan0mon", max_rssi_history: int = 50) -> None:
        self.interface = interface
        self._max_rssi_history = max_rssi_history
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._devices: dict[str, ProbeDevice] = {}
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[ProbeSighting], None]] = []

    def on_probe(self, callback: Callable[[ProbeSighting], None]) -> None:
        """Register a callback for observed probe requests."""
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start probe request monitoring."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="floorplan-probe-tracker",
        )
        self._thread.start()
        logger.info("Probe tracker started on %s", self.interface)

    def stop(self) -> None:
        """Stop probe request monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def get_devices(self) -> list[ProbeDevice]:
        """Get all observed devices."""
        with self._lock:
            return list(self._devices.values())

    def _capture_loop(self) -> None:
        """Capture probe requests using scapy."""
        try:
            from scapy.all import sniff, Dot11, Dot11ProbeReq, Dot11Elt, RadioTap
        except ImportError:
            logger.error("scapy not available for probe tracking")
            return

        def process_packet(pkt: object) -> None:
            if not self._running:
                return
            try:
                self._process_probe(pkt)
            except Exception as e:
                logger.debug("Probe processing error: %s", e)

        try:
            sniff(
                iface=self.interface,
                prn=process_packet,
                store=False,
                stop_filter=lambda _: not self._running,
                monitor=True,
                lfilter=lambda p: p.haslayer(Dot11ProbeReq),
            )
        except Exception as e:
            logger.error("Probe sniff error: %s", e)

    def _process_probe(self, pkt: object) -> None:
        """Process a captured probe request frame."""
        from scapy.all import Dot11, Dot11Elt, RadioTap

        dot11 = pkt.getlayer(Dot11)
        mac = dot11.addr2
        if not mac:
            return

        mac = mac.lower()
        is_randomized = self._is_randomized_mac(mac)

        # Extract SSID
        ssid = None
        elt = pkt.getlayer(Dot11Elt)
        while elt:
            if elt.ID == 0 and elt.info:
                try:
                    ssid = elt.info.decode("utf-8", errors="ignore")
                except Exception:
                    pass
                break
            elt = elt.payload.getlayer(Dot11Elt) if elt.payload else None

        # Extract RSSI
        rssi = -100
        if pkt.haslayer(RadioTap):
            rt = pkt.getlayer(RadioTap)
            rssi = getattr(rt, "dBm_AntSignal", -100) or -100

        # Extract channel
        channel = 0
        if pkt.haslayer(RadioTap):
            rt = pkt.getlayer(RadioTap)
            freq = getattr(rt, "ChannelFrequency", 0) or 0
            if freq:
                channel = self._freq_to_channel(freq)

        now = time.time()
        sighting = ProbeSighting(
            mac=mac,
            ssid=ssid,
            rssi_dbm=rssi,
            channel=channel,
            timestamp=now,
            is_randomized_mac=is_randomized,
        )

        with self._lock:
            if mac not in self._devices:
                self._devices[mac] = ProbeDevice(mac=mac, is_randomized_mac=is_randomized)
            dev = self._devices[mac]
            dev.sighting_count += 1
            dev.last_seen = now
            if ssid:
                dev.ssids_probed.add(ssid)
            if channel:
                dev.channels_seen.add(channel)
            dev.rssi_history.append((now, rssi))
            if len(dev.rssi_history) > self._max_rssi_history:
                dev.rssi_history = dev.rssi_history[-self._max_rssi_history:]

        for cb in self._callbacks:
            try:
                cb(sighting)
            except Exception as e:
                logger.error("Probe callback error: %s", e)

    @staticmethod
    def _is_randomized_mac(mac: str) -> bool:
        """Check if a MAC address is locally administered (randomized).

        The second least significant bit of the first octet indicates
        locally administered (1 = random, 0 = globally unique).
        """
        first_octet = int(mac.split(":")[0], 16)
        return bool(first_octet & 0x02)

    @staticmethod
    def _freq_to_channel(freq: int) -> int:
        if freq == 2484:
            return 14
        if 2412 <= freq <= 2472:
            return (freq - 2407) // 5
        if 5180 <= freq <= 5885:
            return (freq - 5000) // 5
        return 0

    def __enter__(self) -> ProbeTracker:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()
