"""Tests for device fingerprinting."""

from floorplan.tracking.fingerprint import DeviceFingerprint, DeviceSignature


class TestDeviceFingerprint:
    """Test fingerprint matching across MAC changes."""

    def test_exact_match(self):
        """Identical signatures should match exactly."""
        fp = DeviceFingerprint()
        sig = DeviceSignature(
            supported_rates=(6.0, 12.0, 24.0),
            ht_capable=True,
            vht_capable=True,
            he_capable=False,
            ssids_probed=frozenset({"MyWifi", "GuestNet"}),
        )
        fp.register("device-001", sig)

        match = fp.identify(sig)
        assert match == "device-001"

    def test_similar_match(self):
        """Similar signatures should match above threshold."""
        fp = DeviceFingerprint(similarity_threshold=0.5)
        sig1 = DeviceSignature(
            supported_rates=(6.0, 12.0, 24.0, 48.0),
            ht_capable=True,
            vht_capable=True,
            he_capable=False,
            ssids_probed=frozenset({"MyWifi", "GuestNet", "CoffeeShop"}),
        )
        fp.register("device-001", sig1)

        # Slightly different signature (same device, new scan)
        sig2 = DeviceSignature(
            supported_rates=(6.0, 12.0, 24.0, 48.0),
            ht_capable=True,
            vht_capable=True,
            he_capable=False,
            ssids_probed=frozenset({"MyWifi", "GuestNet"}),  # one fewer SSID
        )
        match = fp.identify(sig2)
        assert match == "device-001"

    def test_no_match(self):
        """Very different signatures should not match."""
        fp = DeviceFingerprint(similarity_threshold=0.7)
        sig1 = DeviceSignature(
            supported_rates=(6.0, 12.0),
            ht_capable=True,
            vht_capable=False,
            he_capable=False,
        )
        fp.register("device-001", sig1)

        sig2 = DeviceSignature(
            supported_rates=(54.0,),
            ht_capable=False,
            vht_capable=True,
            he_capable=True,
            ssids_probed=frozenset({"DifferentNetwork"}),
        )
        match = fp.identify(sig2)
        assert match is None

    def test_fingerprint_hash_stable(self):
        """Same signature should produce same hash."""
        sig1 = DeviceSignature(
            supported_rates=(6.0, 12.0),
            ht_capable=True,
        )
        sig2 = DeviceSignature(
            supported_rates=(6.0, 12.0),
            ht_capable=True,
        )
        assert sig1.fingerprint == sig2.fingerprint

    def test_fingerprint_hash_different(self):
        """Different signatures should produce different hashes."""
        sig1 = DeviceSignature(supported_rates=(6.0,), ht_capable=True)
        sig2 = DeviceSignature(supported_rates=(6.0,), ht_capable=False)
        assert sig1.fingerprint != sig2.fingerprint
