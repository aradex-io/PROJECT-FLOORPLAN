"""Passive FTM frame capture — monitor FTM exchanges between other devices.

Captures 802.11mc FTM Action frames in monitor mode using scapy. Extracts
initiator/responder MACs, dialog tokens, and timing information.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 802.11 Action frame categories and FTM action codes
ACTION_CATEGORY_PUBLIC = 4
FTM_ACTION_REQUEST = 32  # Initial FTM Request
FTM_ACTION_RESPONSE = 33  # Initial FTM Response
FTM_ACTION_MEASUREMENT = 34  # FTM Measurement frame


@dataclass
class FTMExchange:
    """Observed FTM exchange between two devices."""

    initiator_mac: str
    responder_mac: str
    channel: int
    dialog_token: int
    request_timestamp: float
    response_timestamp: float | None = None
    burst_count: int = 0
    last_seen: float = field(default_factory=time.time)


@dataclass
class PassiveDevice:
    """A device observed performing FTM exchanges."""

    mac: str
    is_initiator: bool
    is_responder: bool
    exchange_count: int = 0
    peers: set[str] = field(default_factory=set)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    channels: set[int] = field(default_factory=set)


class FTMCapture:
    """Captures and analyzes FTM frames from monitor mode.

    Uses scapy's sniff() to capture 802.11 management frames and filters
    for FTM Action frames (category 4, action codes 32-34).
    """

    def __init__(self, interface: str = "wlan0mon") -> None:
        self.interface = interface
        self._running = False
        self._thread: threading.Thread | None = None

        # Observed state
        self._exchanges: dict[tuple[str, str], FTMExchange] = {}
        self._devices: dict[str, PassiveDevice] = {}
        self._lock = threading.Lock()

        # Callbacks
        self._callbacks: list[Callable[[FTMExchange], None]] = []

    def on_exchange(self, callback: Callable[[FTMExchange], None]) -> None:
        """Register a callback for observed FTM exchanges."""
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start capturing FTM frames in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="floorplan-ftm-capture",
        )
        self._thread.start()
        logger.info("FTM capture started on %s", self.interface)

    def stop(self) -> None:
        """Stop capturing FTM frames."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("FTM capture stopped")

    def get_devices(self) -> list[PassiveDevice]:
        """Get all observed devices."""
        with self._lock:
            return list(self._devices.values())

    def get_exchanges(self) -> list[FTMExchange]:
        """Get all observed FTM exchanges."""
        with self._lock:
            return list(self._exchanges.values())

    def _capture_loop(self) -> None:
        """Capture loop using scapy sniff."""
        try:
            from scapy.all import Dot11, Dot11Action, RadioTap, sniff  # noqa: F401
        except ImportError:
            logger.error("scapy not available — cannot capture FTM frames")
            return

        def process_packet(pkt: object) -> None:
            if not self._running:
                return
            try:
                self._process_frame(pkt)
            except Exception as e:
                logger.debug("Error processing frame: %s", e)

        logger.info("Starting scapy sniff on %s", self.interface)
        try:
            sniff(
                iface=self.interface,
                prn=process_packet,
                store=False,
                stop_filter=lambda _: not self._running,
                monitor=True,
            )
        except Exception as e:
            logger.error("Sniff error: %s", e)

    def _process_frame(self, pkt: Any) -> None:
        """Process a captured 802.11 frame for FTM content."""
        from scapy.all import Dot11, Dot11Action, RadioTap

        if not pkt.haslayer(Dot11):
            return

        dot11 = pkt.getlayer(Dot11)

        # Action frames have type=0 (management), subtype=13
        frame_type = dot11.type
        frame_subtype = dot11.subtype
        if frame_type != 0 or frame_subtype != 13:
            return

        # Extract addresses
        addr1 = dot11.addr1  # Receiver
        addr2 = dot11.addr2  # Transmitter
        if not addr1 or not addr2:
            return

        # Get the Action frame body
        if not pkt.haslayer(Dot11Action):
            # Parse raw payload for action frame category
            raw = bytes(dot11.payload)
            if len(raw) < 3:
                return
            category = raw[0]
            action_code = raw[1]
        else:
            action = pkt.getlayer(Dot11Action)
            category = action.category
            action_code = getattr(action, "action", 0)
            raw = bytes(action.payload) if action.payload else b""

        # Check for FTM frames (Public Action category)
        if category != ACTION_CATEGORY_PUBLIC:
            return

        if action_code not in (FTM_ACTION_REQUEST, FTM_ACTION_RESPONSE, FTM_ACTION_MEASUREMENT):
            return

        # Extract channel from RadioTap if available
        channel = 0
        if pkt.haslayer(RadioTap):
            rt = pkt.getlayer(RadioTap)
            freq = getattr(rt, "ChannelFrequency", 0) or 0
            if freq:
                channel = self._freq_to_channel(freq)

        # Parse dialog token (first byte after action code in body)
        dialog_token = raw[2] if len(raw) > 2 else 0

        now = time.time()

        if action_code == FTM_ACTION_REQUEST:
            self._record_exchange(
                initiator=addr2,
                responder=addr1,
                channel=channel,
                dialog_token=dialog_token,
                is_request=True,
                timestamp=now,
            )
        elif action_code in (FTM_ACTION_RESPONSE, FTM_ACTION_MEASUREMENT):
            self._record_exchange(
                initiator=addr1,
                responder=addr2,
                channel=channel,
                dialog_token=dialog_token,
                is_request=False,
                timestamp=now,
            )

    def _record_exchange(
        self,
        initiator: str,
        responder: str,
        channel: int,
        dialog_token: int,
        is_request: bool,
        timestamp: float,
    ) -> None:
        """Record an observed FTM exchange."""
        key = (initiator.lower(), responder.lower())

        with self._lock:
            if key not in self._exchanges:
                self._exchanges[key] = FTMExchange(
                    initiator_mac=initiator.lower(),
                    responder_mac=responder.lower(),
                    channel=channel,
                    dialog_token=dialog_token,
                    request_timestamp=timestamp if is_request else 0.0,
                    response_timestamp=timestamp if not is_request else None,
                )
            else:
                exc = self._exchanges[key]
                exc.last_seen = timestamp
                exc.burst_count += 1
                if not is_request and exc.response_timestamp is None:
                    exc.response_timestamp = timestamp

            # Update device records
            self._update_device(
                initiator, is_initiator=True, peer=responder, channel=channel, ts=timestamp
            )
            self._update_device(
                responder, is_responder=True, peer=initiator, channel=channel, ts=timestamp
            )

        # Notify callbacks
        exchange = self._exchanges[key]
        for cb in self._callbacks:
            try:
                cb(exchange)
            except Exception as e:
                logger.error("FTM capture callback error: %s", e)

    def _update_device(
        self,
        mac: str,
        *,
        is_initiator: bool = False,
        is_responder: bool = False,
        peer: str = "",
        channel: int = 0,
        ts: float = 0.0,
    ) -> None:
        """Update passive device record."""
        mac = mac.lower()
        if mac not in self._devices:
            self._devices[mac] = PassiveDevice(
                mac=mac,
                is_initiator=is_initiator,
                is_responder=is_responder,
            )
        dev = self._devices[mac]
        if is_initiator:
            dev.is_initiator = True
        if is_responder:
            dev.is_responder = True
        dev.exchange_count += 1
        dev.last_seen = ts
        if peer:
            dev.peers.add(peer.lower())
        if channel:
            dev.channels.add(channel)

    @staticmethod
    def _freq_to_channel(freq: int) -> int:
        """Convert frequency in MHz to channel number."""
        if freq == 2484:
            return 14
        if 2412 <= freq <= 2472:
            return (freq - 2407) // 5
        if 5180 <= freq <= 5885:
            return (freq - 5000) // 5
        if 5955 <= freq <= 7115:
            return (freq - 5950) // 5
        return 0

    def __enter__(self) -> FTMCapture:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()
