import pytest
from types import SimpleNamespace
from certbot import errors
from certbot_dns_hetzner_cloud.authenticator import HetznerCloudDNSAuthenticator, relative_name
from certbot_dns_hetzner_cloud.hetzner_cloud_helper import HetznerCloudHelper


def helper_with_zones(*names):
    """HetznerCloudHelper whose project contains the given zones."""
    helper = object.__new__(HetznerCloudHelper)
    helper.client = SimpleNamespace(zones=SimpleNamespace(get_all=lambda: [SimpleNamespace(name=n) for n in names]))
    return helper


@pytest.mark.parametrize("fqdn, zones, expected", [
    ("_acme-challenge.example.com.", ["example.com", "other.com"], "example.com"),
    ("_acme-challenge.sub.example.co.uk", ["example.co.uk"], "example.co.uk"),
    # issue #7: co.ua is a private public suffix, the zone is fenriv.co.ua
    ("_acme-challenge.fenriv.co.ua.", ["fenriv.co.ua"], "fenriv.co.ua"),
    # nested zones: the most specific one wins
    ("_acme-challenge.dev.example.com.", ["example.com", "dev.example.com"], "dev.example.com"),
    # a zone of its own for the challenge
    ("_acme-challenge.example.com.", ["example.com", "_acme-challenge.example.com"], "_acme-challenge.example.com"),
    ("_acme-challenge.EXAMPLE.com.", ["example.com"], "example.com"),
])
def test_find_zone(fqdn, zones, expected):
    assert helper_with_zones(*zones).find_zone(fqdn).name == expected


@pytest.mark.parametrize("fqdn, zones", [
    ("_acme-challenge.example.com.", []),
    ("_acme-challenge.example.com.", ["other.com"]),
    # a zone must match whole labels
    ("_acme-challenge.myexample.com.", ["example.com"]),
])
def test_find_zone_none(fqdn, zones):
    assert helper_with_zones(*zones).find_zone(fqdn) is None


@pytest.mark.parametrize("fqdn, zone, expected", [
    ("_acme-challenge.example.com.", "example.com", "_acme-challenge"),
    ("_acme-challenge.sub.example.com", "example.com", "_acme-challenge.sub"),
    ("_acme-challenge.fenriv.co.ua.", "fenriv.co.ua", "_acme-challenge"),
    ("_acme-challenge.example.com.", "_acme-challenge.example.com", "@"),
])
def test_relative_name(fqdn, zone, expected):
    assert relative_name(fqdn, zone) == expected


def test_perform_without_zone_raises_plugin_error():
    auth = HetznerCloudDNSAuthenticator(config=None, name="dns-hetzner-cloud")
    auth.hetzner_dns_helper = helper_with_zones("other.com")

    with pytest.raises(errors.PluginError, match="No zone for _acme-challenge.example.com"):
        auth._perform("example.com", "_acme-challenge.example.com.", "token")
