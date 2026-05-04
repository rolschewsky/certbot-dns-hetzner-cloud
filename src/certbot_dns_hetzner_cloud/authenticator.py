import logging

import tldextract
from certbot import errors
from certbot.plugins import dns_common
from datetime import datetime, timezone
from certbot_dns_hetzner_cloud.hetzner_cloud_helper import HetznerCloudHelper

DEFAULT_CREDENTIALS_PATH = "/etc/letsencrypt/hetzner-cloud.ini"


def split_validation_name(validation_name: str) -> tuple[str, str]:
    extract = tldextract.extract(validation_name)
    zone_name = extract.top_domain_under_public_suffix
    record_name = validation_name[:-len(zone_name) - 1].rstrip(".")
    return zone_name, record_name


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

    def _perform(self, domain: str, validation_name: str, validation: str) -> None:
        if not self.hetzner_dns_helper:
            raise errors.PluginError("Hetzner DNS helper not initialized.")

        zone_name, record_name = split_validation_name(validation_name)
        self.logger.info("Adding TXT record %s to zone %s", record_name, zone_name)
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.hetzner_dns_helper.put_txt_record(
            zone=zone_name,
            name=record_name,
            value=validation,
            comment=f"created by hetzner cloud plugin at {timestamp}",
            ttl=self.ttl
        )

    def _cleanup(self, domain: str, validation_name: str, validation: str) -> None:
        if not self.hetzner_dns_helper:
            return

        zone_name, record_name = split_validation_name(validation_name)
        self.logger.info("Removing TXT record %s from zone %s", record_name, zone_name)
        self.hetzner_dns_helper.delete_txt_record(
            zone=zone_name,
            name=record_name,
            value=validation
        )
