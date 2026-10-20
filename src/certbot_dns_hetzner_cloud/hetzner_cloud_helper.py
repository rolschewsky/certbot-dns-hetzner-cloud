from typing import Union

from hcloud import Client, APIException
from hcloud.zones import BoundZone, ZoneRecord, ZoneRRSet
from hcloud.zones.domain import CreateZoneRRSetResponse

class HetznerCloudHelper:
    """Helper class to manage Hetzner Cloud DNS records."""

    def __init__(self, api_key: str) -> None:
        self.client = Client(api_key)

    def _ensure_zone(self, zone: Union[str, BoundZone]) -> BoundZone:
        if isinstance(zone, BoundZone):
            return zone
        return self.client.zones.get(zone)

    def delete_txt_record(self, zone: Union[str, BoundZone], name: str, value: str | None = None) -> None:
        """Delete a TXT record or a specific value from it.
        
        If value is provided, only removes that specific value from the record set.
        If value is None, deletes all TXT records with the given name.
        """
        # ensure value is quoted if provided
        if value is not None and not (value.startswith("\"") and value.endswith("\"")):
            value = f'"{value}"'

        # load zone object
        bound_zone = self._ensure_zone(zone)

        # search for an existing TXT record
        query_result = self.client.zones.get_rrset_list(zone=bound_zone, name=name, type="TXT")

        # delete if exists
        if len(query_result.rrsets) > 0:
            # remove only the specific value from the RecordSet or all if value is None
            records_to_delete = [record for record in query_result.rrsets[0].records if
                                 value is None or record.value == value]
            if len(records_to_delete) > 0:
                # This API will also remove the whole rrset if no record is left
                r = self.client.zones.remove_rrset_records(
                    rrset=query_result.rrsets[0],
                    records=records_to_delete,
                )
                r.wait_until_finished()

    def put_txt_record(self, zone: Union[str, BoundZone], name: str, value: str,
                       comment: str | None = None, ttl: int | None = 60) -> CreateZoneRRSetResponse:
        """Create or update a TXT record."""
        # ensure value is quoted
        if not (value.startswith("\"") and value.endswith("\"")):
            value = f'"{value}"'

        # load zone object
        bound_zone = self._ensure_zone(zone)

        try:
            r = self.client.zones.add_rrset_records(
                rrset=ZoneRRSet(zone=bound_zone, name=name, type="TXT"),
                records=[ZoneRecord(value=value, comment=comment)],
                ttl=ttl)
            r.wait_until_finished()
        except APIException as e:
            if e.code == 'invalid_input' and e.message.startswith('duplicate value'):
                # if it's already there, we can ignore it
                pass
            else:
                raise e
