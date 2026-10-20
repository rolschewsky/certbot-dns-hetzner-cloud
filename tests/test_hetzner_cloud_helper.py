import pytest
from types import SimpleNamespace

from hcloud import APIException

from certbot_dns_hetzner_cloud.hetzner_cloud_helper import HetznerCloudHelper
import certbot_dns_hetzner_cloud.hetzner_cloud_helper as mod

# ---- Test-Doubles ----

class FakeRRSet:
    def __init__(self, name, *values):
        self.name = name
        # Support multiple values: each can be a string or tuple (value, comment)
        self.records = []
        for v in values:
            if isinstance(v, tuple):
                value, comment = v
            else:
                value, comment = v, None
            self.records.append(SimpleNamespace(value=value, comment=comment))

class FakeRRSetListResp:
    def __init__(self, rrsets=None):
        self.rrsets = rrsets or []

class FakeZonesAPI:
    def __init__(self):
        # Aufgerufen-Flags + zuletzt übergebene Argumente
        self.calls = []
        self.bound_zone = SimpleNamespace(id="Z1", name="example.com")

    # Zonen
    def get_all(self):
        self.calls.append(("get_all",))
        return self.all_zones

    def get(self, zone_name):
        self.calls.append(("get", zone_name))
        assert zone_name == "example.com"
        return self.bound_zone

    # RRSet lesen
    def get_rrset_list(self, *, zone, name, type):
        self.calls.append(("get_rrset_list", zone.name, name, type))
        # Rückgabe wird pro Test per Injection gesetzt
        return self._rrset_list

    # RRSet löschen
    def delete_rrset(self, rrset):
        self.calls.append(("delete_rrset", rrset.name))

    # RRSet erstellen
    def create_rrset(self, *, zone, name, type, records):
        self.calls.append(("create_rrset", zone.name, name, type, tuple(r.value for r in records)))
        # Minimal-Response mit rrset zurückgeben (ähnlich hcloud)
        return SimpleNamespace(rrset=FakeRRSet(name, records[0].value))

    def remove_rrset_records(self, rrset, records):
        self.calls.append(("remove_rrset_records", rrset.name, tuple(r.value for r in records)))
        return SimpleNamespace(wait_until_finished=lambda: None)

    def add_rrset_records(self, rrset, records, ttl=None):
        # hcloud only sends the ttl parameter, a ttl on the rrset object is ignored
        self.calls.append(("add_rrset_records", rrset.zone.name, rrset.name, rrset.type, ttl, tuple(r.value for r in records)))
        # Simulate duplicate value
        if records[0].value == 'abc1234':
            raise APIException(code="invalid_input", message="duplicate value ..", details=None)
        return SimpleNamespace(wait_until_finished=lambda: None)

class FakeClient:
    def __init__(self):
        self.zones = FakeZonesAPI()

class FakeBoundZone:
    def __init__(self, name="example.com", id_="Z1"):
        self.name = name
        self.id = id_

# ---- Fixtures ----

@pytest.fixture
def helper(monkeypatch):
    # 1) Hetzner-Client faken
    def fake_init(self, api_key: str):
        self.client = FakeClient()
    monkeypatch.setattr(HetznerCloudHelper, "__init__", fake_init)

    # 2) BoundZone-Klasse im Modul patchen, damit isinstance(...) True ist
    monkeypatch.setattr(mod, "BoundZone", FakeBoundZone)

    # 3) Instanz + Default-BoundZone setzen
    h = HetznerCloudHelper("DUMMY")
    h.client.zones.bound_zone = FakeBoundZone(name="example.com", id_="Z1")

    # (optional) leere RRSet-Liste als Default
    h.client.zones._rrset_list = FakeRRSetListResp([])

    return h

# ---- Tests ----

def test_ensure_zone_with_string(helper):
    zones = helper.client.zones
    zones._rrset_list = FakeRRSetListResp([])  # default

    z = helper._ensure_zone("example.com")
    assert z.name == "example.com"
    assert ("get", "example.com") in zones.calls

def test_ensure_zone_with_boundzone(helper, monkeypatch):
    zones = helper.client.zones
    zones._rrset_list = FakeRRSetListResp([])

    # make BoundZone isinstance(...) pass
    monkeypatch.setattr(mod, "BoundZone", FakeBoundZone)

    bound = FakeBoundZone(name="example.com", id_="Z1")
    zones.bound_zone = bound  # our fake bound zone

    z = helper._ensure_zone(bound)

    assert z is bound
    assert z.name == "example.com"
    assert not any(c[0] == "get" for c in zones.calls)

def test_delete_txt_record_deletes_when_present(helper):
    zones = helper.client.zones
    # Simuliere vorhandenes RRSet
    zones._rrset_list = FakeRRSetListResp([FakeRRSet("_acme-challenge", '"old"')])

    helper.delete_txt_record("example.com", "_acme-challenge")

    # Erwartung: get -> get_rrset_list -> delete_rrset
    assert ("get", "example.com") in zones.calls
    assert ("get_rrset_list", "example.com", "_acme-challenge", "TXT") in zones.calls
    assert ("remove_rrset_records", "_acme-challenge", ('"old"',)) in zones.calls

def test_delete_txt_record_noop_when_absent(helper):
    zones = helper.client.zones
    zones._rrset_list = FakeRRSetListResp([])

    helper.delete_txt_record("example.com", "_acme-challenge")

    # Kein delete_rrset-Call
    assert ("get_rrset_list", "example.com", "_acme-challenge", "TXT") in zones.calls
    assert not [c for c in zones.calls if c[0] == "remove_rrset_records"]

def test_put_txt_record_quotes_value_and_replaces(helper):
    zones = helper.client.zones
    helper.put_txt_record("example.com", "_acme-challenge", value="abc123", comment="test")

    # Reihenfolge prüfen: get → add_rrset_records
    names = [c[0] for c in zones.calls]
    assert names[:2] == ["get", "add_rrset_records"]

    # add_rrset_records wurde mit gequotetem Value aufgerufen:
    create_call = [c for c in zones.calls if c[0] == "add_rrset_records"][-1]
    _, zone_name, rr_name, rr_type, rr_ttl, values = create_call
    assert zone_name == "example.com"
    assert rr_name == "_acme-challenge"
    assert rr_type == "TXT"
    assert rr_ttl == 60
    # we only create the new values
    assert values == ('"abc123"',)

def test_put_txt_record_avoids_duplicates(helper):
    zones = helper.client.zones
    # Record with same value already exists
    helper.put_txt_record("example.com", "_acme-challenge", value="abc1234", comment="test")

def test_delete_txt_record_with_value_removes_only_that_value(helper):
    zones = helper.client.zones
    # Multiple records exist
    zones._rrset_list = FakeRRSetListResp([FakeRRSet("_acme-challenge", '"token1"', '"token2"')])

    helper.delete_txt_record("example.com", "_acme-challenge", value="token1")

    # Should remove only token1, leaving token2 intact
    assert ("remove_rrset_records", "_acme-challenge", ('"token1"',)) in zones.calls

def test_delete_txt_record_without_value_deletes_all(helper):
    zones = helper.client.zones
    # Multiple records exist
    zones._rrset_list = FakeRRSetListResp([FakeRRSet("_acme-challenge", '"token1"', '"token2"')])

    helper.delete_txt_record("example.com", "_acme-challenge", value=None)

    # Should delete entire rrset without recreation
    assert ("remove_rrset_records", "_acme-challenge", ('"token1"', '"token2"')) in zones.calls
