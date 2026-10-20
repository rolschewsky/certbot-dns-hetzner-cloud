import pytest
from types import SimpleNamespace
from certbot_dns_hetzner_cloud.authenticator import HetznerCloudDNSAuthenticator


class DummyHelper:
    """Mock helper that records delete_txt_record calls."""
    def __init__(self):
        self.delete_calls = []

    def find_zone(self, fqdn):
        return SimpleNamespace(name="example.com")

    def delete_txt_record(self, *, zone, name: str, value: str = None):
        self.delete_calls.append((zone.name, name, value))


@pytest.fixture
def authenticator(config):
    """Fixture that sets up an Authenticator with a mocked Hetzner helper."""
    auth = HetznerCloudDNSAuthenticator(config=config, name="dns-hetzner-cloud")

    # Replace the real helper with our dummy mock
    dummy = DummyHelper()
    auth.hetzner_dns_helper = dummy

    return auth, dummy


def test_cleanup_removes_correct_txt_record(authenticator):
    """
    _cleanup() should call delete_txt_record() with the correct zone and record name
    derived from the validation name.
    """
    auth, dummy = authenticator

    # Example DNS-01 challenge details
    domain = "example.com"
    validation_name = "_acme-challenge.sub.example.com."
    validation_value = "abcdef123456"  # not used by cleanup, but Certbot provides it

    # Act: perform the cleanup
    auth._cleanup(domain, validation_name, validation_value)

    # Assert: exactly one delete call was made
    assert len(dummy.delete_calls) == 1, "expected exactly one TXT record deletion call"

    # Extract the call arguments
    zone, name, value = dummy.delete_calls[0]

    # Zone should be the registered domain
    assert zone == "example.com", f"unexpected zone: {zone}"
    # Record name should be relative within the zone
    assert name == "_acme-challenge.sub", f"unexpected record name: {name}"
    # Value should match the validation token
    assert value == validation_value, f"unexpected value: {value}"
