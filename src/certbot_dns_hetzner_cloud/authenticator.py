import logging

import dns.exception
import dns.resolver
from certbot import errors
from certbot.plugins import dns_common
from datetime import datetime, timezone
from certbot_dns_hetzner_cloud.hetzner_cloud_helper import HetznerCloudHelper

DEFAULT_CREDENTIALS_PATH = "/etc/letsencrypt/hetzner-cloud.ini"


def relative_name(fqdn: str, zone_name: str) -> str:
    """Returns fqdn relative to zone_name, "@" for the zone apex."""
    return fqdn.rstrip(".").lower()[:-len(zone_name)].rstrip(".") or "@"


def resolve_cname(name: str) -> str:
    """Follows the CNAME records of name and returns the name they finally point to."""
    try:
        return dns.resolver.canonical_name(name).to_text(omit_final_dot=True)
    except dns.exception.DNSException as e:
        raise errors.PluginError(f"Could not resolve CNAME of {name}: {e}") from e


def parse_bool(value: str) -> bool:
    if value.lower() in ("true", "yes", "on", "1"):
        return True
    if value.lower() in ("false", "no", "off", "0"):
        return False
    raise ValueError(value)


class HetznerCloudDNSAuthenticator(dns_common.DNSAuthenticator):
    description = "Plugin for handling DNS-01 challenges via Hetzner Cloud DNS API."
    ttl = 60

    # Options that can also be set in the credentials file, with their parser.
    credentials_file_options = {"propagation-seconds": int, "follow-cname": parse_bool}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.hetzner_dns_helper: HetznerCloudHelper | None = None
        self.credentials: dns_common.CredentialsConfiguration | None = None

    @classmethod
    def add_parser_arguments(cls, add, default_propagation_seconds=30):
        super().add_parser_arguments(add, default_propagation_seconds)
        add("credentials",
                        help="Path to Hetzner Cloud plugin configuration file.",
            default=DEFAULT_CREDENTIALS_PATH)
        add("follow-cname", action="store_true", default=False,
            help="Follow a CNAME on _acme-challenge.<domain> and create the TXT record in the zone it points to.")

    def more_info(self) -> str:
        return f"""\
    {self.description}
    You must provide an API token via a credentials INI file (default: {DEFAULT_CREDENTIALS_PATH}).
    See https://github.com/rolschewsky/certbot-dns-hetzner-cloud for details.
    """

    def conf(self, var: str):
        # A value from the command line or cli.ini wins, then the credentials file, then the default.
        # Reading the file here instead of writing it into self.config keeps it out of the renewal
        # configuration, so a changed credentials file takes effect on the next renewal.
        parse = self.credentials_file_options.get(var)
        if parse and self.credentials and not self.config.set_by_user(self.dest(var)):
            value = self.credentials.conf(var)
            if value is not None:
                try:
                    return parse(value)
                except ValueError:
                    raise errors.PluginError(
                        f"Invalid value '{value}' for {self.dest(var)} in the credentials file.") from None
        return super().conf(var)

    def _setup_credentials(self) -> None:
        self.credentials = self._configure_credentials("credentials", "Hetzner Cloud plugin configuration file", {
            "api_token": "Hetzner Cloud API Token"
        })
        api_token = self.credentials.conf("api_token")
        self.hetzner_dns_helper = HetznerCloudHelper(api_token)

    def _zone_and_record(self, validation_name: str):
        if self.conf("follow-cname"):
            target = resolve_cname(validation_name)
            if target != validation_name.rstrip("."):
                self.logger.info("Following CNAME %s to %s", validation_name, target)
            validation_name = target
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
