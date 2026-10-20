import logging

from certbot import errors
from certbot.plugins import dns_common
from datetime import datetime, timezone
from certbot_dns_hetzner_cloud.hetzner_cloud_helper import HetznerCloudHelper

DEFAULT_CREDENTIALS_PATH = "/etc/letsencrypt/hetzner-cloud.ini"


def relative_name(fqdn: str, zone_name: str) -> str:
    """Returns fqdn relative to zone_name, "@" for the zone apex."""
    return fqdn.rstrip(".").lower()[:-len(zone_name)].rstrip(".") or "@"


class HetznerCloudDNSAuthenticator(dns_common.DNSAuthenticator):
    description = "Plugin for handling DNS-01 challenges via Hetzner Cloud DNS API."
    ttl = 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.hetzner_dns_helper: HetznerCloudHelper | None = None

    @classmethod
    def add_parser_arguments(cls, add, default_propagation_seconds=30):
        super().add_parser_arguments(add, default_propagation_seconds)
        add("credentials",
                        help="Path to Hetzner Cloud plugin configuration file.",
            default=DEFAULT_CREDENTIALS_PATH)

    def more_info(self) -> str:
        return f"""\
    {self.description}
    You must provide an API token via a credentials INI file (default: {DEFAULT_CREDENTIALS_PATH}).
    See https://github.com/rolschewsky/certbot-dns-hetzner-cloud for details.
    """

    def _setup_credentials(self) -> None:
        credentials = self._configure_credentials("credentials", "Hetzner Cloud plugin configuration file", {
            "api_token": "Hetzner Cloud API Token"
        })
        api_token = credentials.conf("api_token")
        self.hetzner_dns_helper = HetznerCloudHelper(api_token)

    def _zone_and_record(self, validation_name: str):
        # The zone is taken from the zones of the project instead of the public suffix list, which does not know
        # zones below private suffixes like co.ua or zones for subdomains.
        zone = self.hetzner_dns_helper.find_zone(validation_name)
        if zone is None:
            raise errors.PluginError(
                f"No zone for {validation_name.rstrip('.')} in the Hetzner Cloud project of the API token.")
        return zone, relative_name(validation_name, zone.name)

    def _perform(self, domain: str, validation_name: str, validation: str) -> None:
        if not self.hetzner_dns_helper:
            raise errors.PluginError("Hetzner DNS helper not initialized.")

        zone, record_name = self._zone_and_record(validation_name)
        self.logger.info("Adding TXT record %s to zone %s", record_name, zone.name)
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.hetzner_dns_helper.put_txt_record(
            zone=zone,
            name=record_name,
            value=validation,
            comment=f"created by hetzner cloud plugin at {timestamp}",
            ttl=self.ttl
        )

    def _cleanup(self, domain: str, validation_name: str, validation: str) -> None:
        if not self.hetzner_dns_helper:
            return

        zone, record_name = self._zone_and_record(validation_name)
        self.logger.info("Removing TXT record %s from zone %s", record_name, zone.name)
        self.hetzner_dns_helper.delete_txt_record(
            zone=zone,
            name=record_name,
            value=validation
        )
