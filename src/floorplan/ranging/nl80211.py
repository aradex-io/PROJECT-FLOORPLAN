"""Low-level nl80211 netlink interface for FTM operations.

This module provides the netlink communication layer for Wi-Fi FTM (Fine Time
Measurement) using the Linux nl80211 interface. It wraps the kernel's FTM
commands: device capability query, FTM initiation, and result retrieval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum

logger = logging.getLogger(__name__)

# nl80211 command constants (from linux/nl80211.h)
NL80211_CMD_GET_WIPHY = 1
NL80211_CMD_GET_INTERFACE = 5
NL80211_CMD_START_PEER_MEASUREMENT = 0x85  # 133
NL80211_CMD_PEER_MEASUREMENT_RESULT = 0x86  # 134
NL80211_CMD_PEER_MEASUREMENT_COMPLETE = 0x87  # 135

# nl80211 attribute constants
NL80211_ATTR_WIPHY = 1
NL80211_ATTR_IFINDEX = 3
NL80211_ATTR_WIPHY_NAME = 4
NL80211_ATTR_MAC = 6
NL80211_ATTR_WIPHY_FREQ = 38
NL80211_ATTR_PEER_MEASUREMENTS = 0x77  # 119

# Peer measurement type
NL80211_PMSR_TYPE_FTM = 1

# FTM request attributes
NL80211_PMSR_FTM_REQ_ATTR_ASAP = 1
NL80211_PMSR_FTM_REQ_ATTR_PREAMBLE = 2
NL80211_PMSR_FTM_REQ_ATTR_NUM_BURSTS_EXP = 3
NL80211_PMSR_FTM_REQ_ATTR_BURST_PERIOD = 4
NL80211_PMSR_FTM_REQ_ATTR_BURST_DURATION = 5
NL80211_PMSR_FTM_REQ_ATTR_FTMS_PER_BURST = 6
NL80211_PMSR_FTM_REQ_ATTR_NUM_FTMR_RETRIES = 7
NL80211_PMSR_FTM_REQ_ATTR_REQUEST_LCI = 8
NL80211_PMSR_FTM_REQ_ATTR_REQUEST_CIVICLOC = 9
NL80211_PMSR_FTM_REQ_ATTR_TRIGGER_BASED = 10
NL80211_PMSR_FTM_REQ_ATTR_NON_TRIGGER_BASED = 11

# FTM result attributes
NL80211_PMSR_FTM_RESP_ATTR_FAIL_REASON = 1
NL80211_PMSR_FTM_RESP_ATTR_BURST_INDEX = 2
NL80211_PMSR_FTM_RESP_ATTR_NUM_FTMR_ATTEMPTS = 3
NL80211_PMSR_FTM_RESP_ATTR_NUM_FTMR_SUCCESSES = 4
NL80211_PMSR_FTM_RESP_ATTR_BUSY_RETRY_TIME = 5
NL80211_PMSR_FTM_RESP_ATTR_NUM_BURSTS_EXP = 6
NL80211_PMSR_FTM_RESP_ATTR_BURST_DURATION = 7
NL80211_PMSR_FTM_RESP_ATTR_FTMS_PER_BURST = 8
NL80211_PMSR_FTM_RESP_ATTR_RSSI_AVG = 9
NL80211_PMSR_FTM_RESP_ATTR_RSSI_SPREAD = 10
NL80211_PMSR_FTM_RESP_ATTR_RTT_AVG = 13
NL80211_PMSR_FTM_RESP_ATTR_RTT_VARIANCE = 14
NL80211_PMSR_FTM_RESP_ATTR_RTT_SPREAD = 15
NL80211_PMSR_FTM_RESP_ATTR_DIST_AVG = 16
NL80211_PMSR_FTM_RESP_ATTR_DIST_VARIANCE = 17
NL80211_PMSR_FTM_RESP_ATTR_DIST_SPREAD = 18

# Preamble types
NL80211_PREAMBLE_HT = 2
NL80211_PREAMBLE_VHT = 3
NL80211_PREAMBLE_HE = 5

# Channel bandwidth
NL80211_CHAN_WIDTH_20 = 1
NL80211_CHAN_WIDTH_40 = 2
NL80211_CHAN_WIDTH_80 = 3
NL80211_CHAN_WIDTH_160 = 5


class FTMFailReason(IntEnum):
    """Reasons an FTM measurement can fail."""

    UNSPECIFIED = 0
    NO_RESPONSE = 1
    REJECTED = 2
    WRONG_CHANNEL = 3
    PEER_NOT_CAPABLE = 4
    INVALID_TIMESTAMP = 5
    PEER_BUSY = 6
    TIMEOUT = 7


@dataclass
class FTMResult:
    """Raw FTM measurement result from nl80211."""

    target_mac: str
    rtt_avg_ps: int  # picoseconds
    rtt_variance_ps: int
    rtt_spread_ps: int
    dist_avg_mm: int  # millimeters
    dist_variance_mm: int
    dist_spread_mm: int
    rssi_avg_dbm: int
    rssi_spread_dbm: int
    burst_index: int
    num_ftmr_attempts: int
    num_ftmr_successes: int
    fail_reason: FTMFailReason | None = None


class NL80211Interface:
    """Interface to nl80211 for FTM operations via pyroute2.

    This class provides methods to:
    - Query device FTM capabilities
    - Initiate FTM measurements to target devices
    - Parse FTM measurement results
    """

    def __init__(self, interface: str = "wlan0") -> None:
        self.interface = interface
        self._ifindex: int | None = None
        self._phy_index: int | None = None
        self._nl_socket: object = None

    def _get_ifindex(self) -> int:
        """Get the interface index for the Wi-Fi device."""
        if self._ifindex is not None:
            return self._ifindex
        try:
            with open(f"/sys/class/net/{self.interface}/ifindex") as f:
                self._ifindex = int(f.read().strip())
            return self._ifindex
        except FileNotFoundError:
            raise RuntimeError(f"Interface {self.interface} not found") from None

    def _get_phy_index(self) -> int:
        """Get the phy index for the Wi-Fi device."""
        if self._phy_index is not None:
            return self._phy_index
        try:
            with open(f"/sys/class/net/{self.interface}/phy80211/index") as f:
                self._phy_index = int(f.read().strip())
            return self._phy_index
        except FileNotFoundError:
            raise RuntimeError(
                f"Interface {self.interface} has no phy80211 — not a Wi-Fi device"
            ) from None

    def connect(self) -> None:
        """Establish netlink connection for nl80211 communication."""
        try:
            from pyroute2.netlink.nl80211 import NL80211

            self._nl_socket = NL80211()
            self._nl_socket.bind()
            logger.info("Connected to nl80211 via netlink on %s", self.interface)
        except ImportError:
            logger.warning(
                "pyroute2 not available — using simulated nl80211 interface. "
                "Install pyroute2 for real hardware access."
            )
            self._nl_socket = None
        except Exception as e:
            logger.warning("Failed to bind nl80211 socket: %s — using simulation", e)
            self._nl_socket = None

    def close(self) -> None:
        """Close the netlink connection."""
        if self._nl_socket is not None and hasattr(self._nl_socket, "close"):
            self._nl_socket.close()
            self._nl_socket = None

    def check_ftm_support(self) -> dict[str, bool]:
        """Check if the interface supports FTM initiator and/or responder."""
        result = {
            "ftm_initiator": False,
            "ftm_responder": False,
        }
        # Try reading from sysfs/nl80211 phy info
        try:
            phy_idx = self._get_phy_index()
            phy_name = f"phy{phy_idx}"
            # Parse phy capabilities from nl80211 or /sys
            if self._nl_socket is not None:
                msg = self._nl_socket.get(
                    NL80211_CMD_GET_WIPHY,
                    attrs=[("NL80211_ATTR_WIPHY", phy_idx)],
                )
                # Parse PMSR capabilities from response
                for m in msg:
                    attrs = dict(m.get("attrs", []))
                    if "NL80211_ATTR_PEER_MEASUREMENTS" in attrs:
                        result["ftm_initiator"] = True
                        logger.info("FTM initiator support detected on %s", phy_name)
            else:
                logger.info("Simulated mode: reporting FTM support as available")
                result["ftm_initiator"] = True
                result["ftm_responder"] = True
        except Exception as e:
            logger.debug("FTM capability check failed: %s", e)

        return result

    def start_ftm_measurement(
        self,
        target_mac: str,
        channel: int,
        *,
        num_bursts_exp: int = 2,
        ftms_per_burst: int = 8,
        burst_period_ms: int = 200,
        asap: bool = True,
        preamble: int = NL80211_PREAMBLE_HT,
        bandwidth: int = NL80211_CHAN_WIDTH_20,
    ) -> list[FTMResult] | None:
        """Initiate an FTM measurement to a target device.

        Args:
            target_mac: MAC address of the FTM responder.
            channel: Wi-Fi channel frequency in MHz.
            num_bursts_exp: Exponent for number of bursts (actual = 2^exp).
            ftms_per_burst: Number of FTM frames per burst.
            burst_period_ms: Time between bursts in milliseconds.
            asap: Use ASAP mode (no scheduling).
            preamble: Preamble type (HT, VHT, HE).
            bandwidth: Channel bandwidth.

        Returns:
            List of FTMResult for each burst, or None on failure.
        """
        mac_bytes = bytes.fromhex(target_mac.replace(":", ""))
        if len(mac_bytes) != 6:
            raise ValueError(f"Invalid MAC address: {target_mac}")

        if self._nl_socket is None:
            logger.info("Simulated FTM measurement to %s on channel %d", target_mac, channel)
            return self._simulate_ftm(target_mac, num_bursts_exp, ftms_per_burst)

        try:
            ifindex = self._get_ifindex()
            # Build the nested FTM request attributes
            # This uses the NL80211_CMD_START_PEER_MEASUREMENT command
            ftm_req_attrs = {
                "NL80211_PMSR_FTM_REQ_ATTR_ASAP": asap,
                "NL80211_PMSR_FTM_REQ_ATTR_PREAMBLE": preamble,
                "NL80211_PMSR_FTM_REQ_ATTR_NUM_BURSTS_EXP": num_bursts_exp,
                "NL80211_PMSR_FTM_REQ_ATTR_BURST_PERIOD": burst_period_ms,
                "NL80211_PMSR_FTM_REQ_ATTR_FTMS_PER_BURST": ftms_per_burst,
            }
            peer_attrs = {
                "NL80211_ATTR_MAC": mac_bytes,
                "NL80211_ATTR_WIPHY_FREQ": channel,
                "NL80211_PMSR_PEER_ATTR_CHAN": {
                    "NL80211_ATTR_WIPHY_FREQ": channel,
                    "NL80211_ATTR_CHANNEL_WIDTH": bandwidth,
                },
                "NL80211_PMSR_PEER_ATTR_REQ": {
                    "NL80211_PMSR_REQ_ATTR_DATA": {
                        "NL80211_PMSR_TYPE_FTM": ftm_req_attrs,
                    },
                },
            }
            # Send the measurement request
            self._nl_socket.put(
                NL80211_CMD_START_PEER_MEASUREMENT,
                attrs=[
                    ("NL80211_ATTR_IFINDEX", ifindex),
                    ("NL80211_ATTR_PEER_MEASUREMENTS", {"peers": [peer_attrs]}),
                ],
            )
            # Wait for results (blocking)
            results = self._receive_ftm_results(target_mac)
            return results

        except Exception as e:
            logger.error("FTM measurement to %s failed: %s", target_mac, e)
            return None

    def _receive_ftm_results(self, target_mac: str) -> list[FTMResult]:
        """Wait for and parse FTM measurement results from netlink."""
        results: list[FTMResult] = []
        if self._nl_socket is None:
            return results

        while True:
            try:
                msgs = self._nl_socket.get()
                for msg in msgs:
                    cmd = msg.get("cmd", 0)
                    if cmd == NL80211_CMD_PEER_MEASUREMENT_RESULT:
                        result = self._parse_ftm_result(msg, target_mac)
                        if result:
                            results.append(result)
                    elif cmd == NL80211_CMD_PEER_MEASUREMENT_COMPLETE:
                        return results
            except Exception as e:
                logger.error("Error receiving FTM results: %s", e)
                break

        return results

    def _parse_ftm_result(self, msg: dict, target_mac: str) -> FTMResult | None:
        """Parse a single FTM result from a netlink message."""
        try:
            attrs = dict(msg.get("attrs", []))
            pmsr = attrs.get("NL80211_ATTR_PEER_MEASUREMENTS", {})
            peers = pmsr.get("peers", [])
            for peer in peers:
                resp = peer.get("NL80211_PMSR_PEER_ATTR_RESP", {})
                ftm_data = resp.get("NL80211_PMSR_RESP_ATTR_DATA", {}).get(
                    "NL80211_PMSR_TYPE_FTM", {}
                )
                if not ftm_data:
                    continue

                fail = ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_FAIL_REASON")
                if fail is not None and fail != 0:
                    return FTMResult(
                        target_mac=target_mac,
                        rtt_avg_ps=0,
                        rtt_variance_ps=0,
                        rtt_spread_ps=0,
                        dist_avg_mm=0,
                        dist_variance_mm=0,
                        dist_spread_mm=0,
                        rssi_avg_dbm=0,
                        rssi_spread_dbm=0,
                        burst_index=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_BURST_INDEX", 0),
                        num_ftmr_attempts=0,
                        num_ftmr_successes=0,
                        fail_reason=FTMFailReason(fail),
                    )

                return FTMResult(
                    target_mac=target_mac,
                    rtt_avg_ps=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_RTT_AVG", 0),
                    rtt_variance_ps=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_RTT_VARIANCE", 0),
                    rtt_spread_ps=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_RTT_SPREAD", 0),
                    dist_avg_mm=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_DIST_AVG", 0),
                    dist_variance_mm=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_DIST_VARIANCE", 0),
                    dist_spread_mm=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_DIST_SPREAD", 0),
                    rssi_avg_dbm=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_RSSI_AVG", 0),
                    rssi_spread_dbm=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_RSSI_SPREAD", 0),
                    burst_index=ftm_data.get("NL80211_PMSR_FTM_RESP_ATTR_BURST_INDEX", 0),
                    num_ftmr_attempts=ftm_data.get(
                        "NL80211_PMSR_FTM_RESP_ATTR_NUM_FTMR_ATTEMPTS", 0
                    ),
                    num_ftmr_successes=ftm_data.get(
                        "NL80211_PMSR_FTM_RESP_ATTR_NUM_FTMR_SUCCESSES", 0
                    ),
                )
        except Exception as e:
            logger.error("Failed to parse FTM result: %s", e)

        return None

    def _simulate_ftm(
        self, target_mac: str, num_bursts_exp: int, ftms_per_burst: int
    ) -> list[FTMResult]:
        """Generate simulated FTM results for testing without hardware."""
        import random

        num_bursts = 2**num_bursts_exp
        results = []
        base_dist_mm = random.randint(1000, 10000)  # 1-10 meters

        for burst_idx in range(num_bursts):
            noise_mm = random.gauss(0, 200)
            dist_mm = int(base_dist_mm + noise_mm)
            rtt_ps = int(dist_mm * 2 / 0.0003)  # d = c*t/2, t = 2d/c

            results.append(
                FTMResult(
                    target_mac=target_mac,
                    rtt_avg_ps=rtt_ps,
                    rtt_variance_ps=abs(int(random.gauss(0, 1000))),
                    rtt_spread_ps=abs(int(random.gauss(0, 500))),
                    dist_avg_mm=dist_mm,
                    dist_variance_mm=abs(int(random.gauss(0, 400))),
                    dist_spread_mm=abs(int(random.gauss(0, 200))),
                    rssi_avg_dbm=random.randint(-80, -30),
                    rssi_spread_dbm=random.randint(1, 5),
                    burst_index=burst_idx,
                    num_ftmr_attempts=ftms_per_burst,
                    num_ftmr_successes=max(1, ftms_per_burst - random.randint(0, 2)),
                )
            )

        return results

    def __enter__(self) -> NL80211Interface:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
