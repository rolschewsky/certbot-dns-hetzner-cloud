import pytest
from types import SimpleNamespace


def _make_config(set_by_user=(), **values):
    """Minimal stand-in for Certbot's NamespaceConfig with the plugin defaults."""
    defaults = {"dns_hetzner_cloud_propagation_seconds": 30, "dns_hetzner_cloud_follow_cname": False}
    return SimpleNamespace(**{**defaults, **values}, set_by_user=lambda var: var in set_by_user)


@pytest.fixture
def make_config():
    return _make_config


@pytest.fixture
def config():
    return _make_config()
