from typing import Union

from hcloud import Client
from hcloud.zones import BoundZone, ZoneRecord
from hcloud.zones.domain import CreateZoneRRSetResponse

class HetznerCloudHelper:
    """Helper class to manage Hetzner Cloud DNS records."""

    def __init__(self, api_key: str) -> None:
        self.client = Client(api_key)

    def _ensure_zone(self, zone: Union[str, BoundZone]) -> BoundZone:
        if isinstance(zone, BoundZone):
            return zone
        return self.client.zones.get(zone)

    def delete_txt_record(self, zone: Union[str, BoundZone], name: str) -> None:
        """Delete a TXT record if it exists."""
        # load zone object
        bound_zone = self._ensure_zone(zone)

        # search for an existing TXT record
        query_result = self.client.zones.get_rrset_list(zone=bound_zone, name=name, type="TXT")

        # delete if exists
        if len(query_result.rrsets) > 0:
            self.client.zones.delete_rrset(query_result.rrsets[0])

    def put_txt_record(self, zone: Union[str, BoundZone], name: str, value: str, comment: str | None = None) -> CreateZoneRRSetResponse:
        """Create or update a TXT record."""
        # ensure value is quoted
        if not value.startswith("\"") or not value.endswith("\""):
            value = f'"{value}"'

        # load zone object
        bound_zone = self._ensure_zone(zone)

        # delete old TXT record
        self.delete_txt_record(bound_zone, name)

        # create new TXT record
        return self.client.zones.create_rrset(
            zone=bound_zone,
            name=name,
            type="TXT",
            records=[ZoneRecord(
                value=value,
                comment=comment
            )],
            ttl=60
        )