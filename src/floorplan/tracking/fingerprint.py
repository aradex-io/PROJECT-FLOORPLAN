"""Device fingerprinting — identify devices across MAC randomization.

Uses non-MAC identifying features from FTM responses, probe requests,
and capability fields to create a persistent device signature.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DeviceSignature:
    """Collection of non-MAC identifying features for a device."""

    # From capability fields
    supported_rates: tuple[float, ...] = ()
    ht_capable: bool = False
    vht_capable: bool = False
    he_capable: bool = False

    # From probe requests
    ssids_probed: frozenset[str] = frozenset()

    # Timing characteristics
    avg_ftm_response_time_us: float = 0.0

    # Radio characteristics
    typical_tx_power_dbm: int = 0

    @property
    def fingerprint(self) -> str:
        """Compute a hash fingerprint from all features."""
        components = [
            ",".join(str(r) for r in sorted(self.supported_rates)),
            str(self.ht_capable),
            str(self.vht_capable),
            str(self.he_capable),
            ",".join(sorted(self.ssids_probed)),
            f"{self.avg_ftm_response_time_us:.0f}",
            str(self.typical_tx_power_dbm),
        ]
        raw = "|".join(components)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class DeviceFingerprint:
    """Manages device fingerprinting and identity correlation.

    When a device changes its MAC address, we attempt to match it to a
    previously seen device using its fingerprint signature.
    """

    def __init__(self, similarity_threshold: float = 0.7) -> None:
        self.similarity_threshold = similarity_threshold
        self._signatures: dict[str, DeviceSignature] = {}  # device_id -> signature
        self._fingerprint_index: dict[str, str] = {}  # fingerprint_hash -> device_id

    def register(self, device_id: str, signature: DeviceSignature) -> None:
        """Register or update a device's fingerprint signature."""
        self._signatures[device_id] = signature
        fp = signature.fingerprint
        self._fingerprint_index[fp] = device_id
        logger.debug("Registered fingerprint %s for device %s", fp, device_id)

    def identify(self, signature: DeviceSignature) -> str | None:
        """Attempt to identify a device by its signature.

        Returns:
            The device_id if a match is found, None otherwise.
        """
        # Exact match first
        fp = signature.fingerprint
        if fp in self._fingerprint_index:
            return self._fingerprint_index[fp]

        # Fuzzy matching
        best_match: str | None = None
        best_score = 0.0

        for device_id, known_sig in self._signatures.items():
            score = self._similarity(signature, known_sig)
            if score > best_score and score >= self.similarity_threshold:
                best_score = score
                best_match = device_id

        if best_match:
            logger.info("Fuzzy fingerprint match: score=%.2f → device %s", best_score, best_match)
        return best_match

    def build_signature(
        self,
        *,
        supported_rates: list[float] | None = None,
        ht_capable: bool = False,
        vht_capable: bool = False,
        he_capable: bool = False,
        ssids_probed: set[str] | None = None,
        avg_ftm_response_time_us: float = 0.0,
        typical_tx_power_dbm: int = 0,
    ) -> DeviceSignature:
        """Build a DeviceSignature from observed features."""
        return DeviceSignature(
            supported_rates=tuple(sorted(supported_rates or [])),
            ht_capable=ht_capable,
            vht_capable=vht_capable,
            he_capable=he_capable,
            ssids_probed=frozenset(ssids_probed or set()),
            avg_ftm_response_time_us=avg_ftm_response_time_us,
            typical_tx_power_dbm=typical_tx_power_dbm,
        )

    @staticmethod
    def _similarity(a: DeviceSignature, b: DeviceSignature) -> float:
        """Compute similarity score between two signatures (0.0-1.0)."""
        scores: list[float] = []

        # Supported rates overlap (Jaccard similarity)
        if a.supported_rates or b.supported_rates:
            set_a = set(a.supported_rates)
            set_b = set(b.supported_rates)
            union = set_a | set_b
            if union:
                scores.append(len(set_a & set_b) / len(union))

        # Capability match
        cap_match = sum(
            [
                a.ht_capable == b.ht_capable,
                a.vht_capable == b.vht_capable,
                a.he_capable == b.he_capable,
            ]
        )
        scores.append(cap_match / 3.0)

        # SSID overlap
        if a.ssids_probed or b.ssids_probed:
            union = a.ssids_probed | b.ssids_probed
            if union:
                scores.append(len(a.ssids_probed & b.ssids_probed) / len(union))

        # FTM timing similarity (within 20%)
        if a.avg_ftm_response_time_us > 0 and b.avg_ftm_response_time_us > 0:
            ratio = min(a.avg_ftm_response_time_us, b.avg_ftm_response_time_us) / max(
                a.avg_ftm_response_time_us, b.avg_ftm_response_time_us
            )
            scores.append(ratio)

        if not scores:
            return 0.0
        return sum(scores) / len(scores)
