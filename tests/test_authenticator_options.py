import argparse
import dns.name
import dns.resolver
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock
from certbot import errors
import certbot_dns_hetzner_cloud.authenticator as mod
from certbot_dns_hetzner_cloud.authenticator import HetznerCloudDNSAuthenticator, resolve_cname
from certbot_dns_hetzner_cloud.hetzner_cloud_helper import HetznerCloudHelper


class DummyHelper(HetznerCloudHelper):
    """Helper for a project with the zones example.com and acme-zone.eu that records put and delete calls."""
    def __init__(self, *args):
        zones = [SimpleNamespace(name="example.com"), SimpleNamespace(name="acme-zone.eu")]
        self.client = SimpleNamespace(zones=SimpleNamespace(get_all=lambda: zones))
        self.put_calls = []
        self.delete_calls = []

    def put_txt_record(self, *, zone, name, value, comment, ttl):
        self.put_calls.append((zone.name, name))

    def delete_txt_record(self, *, zone, name, value=None):
        self.delete_calls.append((zone.name, name))


@pytest.fixture
def credentials_file(tmp_path):
    """Writes a credentials file and returns its path; extra lines are appended."""
    def write(*lines):
        path = tmp_path / "hetzner-cloud.ini"
        path.write_text("\n".join(["dns_hetzner_cloud_api_token = token", *lines]) + "\n")
        path.chmod(0o600)
        return str(path)
    return write


@pytest.fixture
def make_authenticator(make_config, credentials_file, monkeypatch):
    """Authenticator with a real credentials file and a mocked Hetzner helper."""
    monkeypatch.setattr(mod, "HetznerCloudHelper", DummyHelper)

    def make(*lines, set_by_user=(), **values):
        config = make_config(set_by_user, dns_hetzner_cloud_credentials=credentials_file(*lines), **values)
        auth = HetznerCloudDNSAuthenticator(config=config, name="dns-hetzner-cloud")
        auth._setup_credentials()
        return auth
    return make


def test_parser_defaults_and_flag():
    parser = argparse.ArgumentParser()
    HetznerCloudDNSAuthenticator.inject_parser_options(parser, "dns-hetzner-cloud")

    defaults = parser.parse_args([])
    assert defaults.dns_hetzner_cloud_propagation_seconds == 30
    assert defaults.dns_hetzner_cloud_follow_cname is False

    given = parser.parse_args(["--dns-hetzner-cloud-propagation-seconds", "90", "--dns-hetzner-cloud-follow-cname"])
    assert given.dns_hetzner_cloud_propagation_seconds == 90
    assert given.dns_hetzner_cloud_follow_cname is True


def test_defaults_without_credentials_file_options(make_authenticator):
    auth = make_authenticator()
    assert auth.conf("propagation-seconds") == 30
    assert auth.conf("follow-cname") is False


def test_credentials_file_overrides_defaults(make_authenticator):
    auth = make_authenticator("dns_hetzner_cloud_propagation_seconds = 120", "dns_hetzner_cloud_follow_cname = yes")
    assert auth.conf("propagation-seconds") == 120
    assert auth.conf("follow-cname") is True


def test_command_line_wins_over_credentials_file(make_authenticator):
    auth = make_authenticator("dns_hetzner_cloud_propagation_seconds = 120",
                              set_by_user={"dns_hetzner_cloud_propagation_seconds"},
                              dns_hetzner_cloud_propagation_seconds=45)
    assert auth.conf("propagation-seconds") == 45


@pytest.mark.parametrize("line", ["dns_hetzner_cloud_propagation_seconds = soon",
                                  "dns_hetzner_cloud_follow_cname = maybe"])
def test_invalid_value_in_credentials_file(make_authenticator, line):
    auth = make_authenticator(line)
    with pytest.raises(errors.PluginError, match="Invalid value"):
        auth.conf(line.split()[0].removeprefix("dns_hetzner_cloud_").replace("_", "-"))


def test_perform_waits_propagation_seconds_from_credentials_file(make_authenticator, monkeypatch):
    auth = make_authenticator("dns_hetzner_cloud_propagation_seconds = 120")
    monkeypatch.setattr(mod.dns_common, "sleep", sleeps := MagicMock())
    monkeypatch.setattr(mod.dns_common.display_util, "notify", MagicMock())
    achall = MagicMock()
    achall.identifier.value = "example.com"
    achall.validation_domain_name.return_value = "_acme-challenge.example.com"

    auth.perform([achall])

    sleeps.assert_called_once_with(120)


def test_follow_cname_writes_into_target_zone(make_authenticator, monkeypatch):
    auth = make_authenticator("dns_hetzner_cloud_follow_cname = true")
    monkeypatch.setattr(mod, "resolve_cname", lambda name: "dev-tt.acme-zone.eu")

    auth._perform("dev.example.com", "_acme-challenge.dev.example.com.", "token")
    auth._cleanup("dev.example.com", "_acme-challenge.dev.example.com.", "token")

    assert auth.hetzner_dns_helper.put_calls == [("acme-zone.eu", "dev-tt")]
    assert auth.hetzner_dns_helper.delete_calls == [("acme-zone.eu", "dev-tt")]


def test_cname_is_not_resolved_by_default(make_authenticator, monkeypatch):
    auth = make_authenticator()
    monkeypatch.setattr(mod, "resolve_cname", MagicMock(side_effect=AssertionError("must not resolve")))

    auth._perform("dev.example.com", "_acme-challenge.dev.example.com.", "token")

    assert auth.hetzner_dns_helper.put_calls == [("example.com", "_acme-challenge.dev")]


def test_resolve_cname_returns_name_without_trailing_dot(monkeypatch):
    monkeypatch.setattr(dns.resolver, "canonical_name", lambda name: dns.name.from_text("dev-tt.acme-zone.eu."))
    assert resolve_cname("_acme-challenge.dev.example.com.") == "dev-tt.acme-zone.eu"


def test_resolve_cname_failure_raises_plugin_error(monkeypatch):
    def fail(name):
        raise dns.resolver.NoNameservers()
    monkeypatch.setattr(dns.resolver, "canonical_name", fail)

    with pytest.raises(errors.PluginError, match="Could not resolve CNAME"):
        resolve_cname("_acme-challenge.dev.example.com.")
