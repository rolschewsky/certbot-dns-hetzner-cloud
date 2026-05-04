import pytest
from datetime import datetime, timezone
from certbot_dns_hetzner_cloud.authenticator import HetznerCloudDNSAuthenticator


class DummyHelper:
    """Mock helper that records all put_txt_record calls."""
    def __init__(self):
        self.put_calls = []

    def put_txt_record(self, *, zone: str, name: str, value: str, comment: str, ttl: int):
        # Basic validation: value should not be quoted (Certbot handles raw TXT values)
        assert not value.startswith('"') and not value.endswith('"')
        self.put_calls.append((zone, name, value, comment, ttl))


@pytest.fixture
def authenticator(monkeypatch):
    """Fixture that sets up an Authenticator with a mocked Hetzner helper."""
    auth = HetznerCloudDNSAuthenticator(config=None, name="dns-hetzner-cloud")

    # Replace the real helper with our dummy mock
    dummy = DummyHelper()
    auth.hetzner_dns_helper = dummy

    return auth, dummy


def test_perform_creates_expected_txt_record(authenticator):
    """_perform() should split validation name, create a TXT record and pass proper values."""

    auth, dummy = authenticator

    # Example data from a real Certbot DNS-01 challenge
    domain = "example.com"
    validation_name = "_acme-challenge.sub.example.com."
    validation_value = "abcdef123456"

    # Act: run the method under test
    auth._perform(domain, validation_name, validation_value)

    # Assert: exactly one API call was made
    assert len(dummy.put_calls) == 1, "expected exactly one TXT record creation call"

    # Unpack recorded call arguments
    zone, name, value, comment, ttl = dummy.put_calls[0]

    # Zone should be the registered domain
    assert zone == "example.com", f"unexpected zone: {zone}"
    # Name should be the subrecord portion
    assert name == "_acme-challenge.sub", f"unexpected record name: {name}"
    # Value should match the validation token (unquoted)
    assert value == validation_value
    # Comment must contain ISO8601 UTC timestamp and plugin marker
    assert "created by hetzner cloud plugin" in comment.lower()
    datetime.fromisoformat(comment.split()[-1].replace("Z", "+00:00"))  # should parse cleanly
    # ttl should be default
    assert ttl == 60
