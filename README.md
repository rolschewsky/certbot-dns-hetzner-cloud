[![GitHub Release](https://img.shields.io/github/v/release/rolschewsky/certbot-dns-hetzner-cloud)](https://github.com/rolschewsky/certbot-dns-hetzner-cloud/releases)
[![PyPI Version](https://img.shields.io/pypi/v/certbot-dns-hetzner-cloud)](https://pypi.org/project/certbot-dns-hetzner-cloud/)
[![Snapcraft Version](https://img.shields.io/snapcraft/v/certbot-dns-hetzner-cloud/latest/stable)](https://snapcraft.io/certbot-dns-hetzner-cloud)
[![License](https://img.shields.io/github/license/rolschewsky/certbot-dns-hetzner-cloud)](https://github.com/rolschewsky/certbot-dns-hetzner-cloud/blob/main/LICENSE.txt)
[![Build Release](https://github.com/rolschewsky/certbot-dns-hetzner-cloud/actions/workflows/build-release.yml/badge.svg)](https://github.com/rolschewsky/certbot-dns-hetzner-cloud/actions/workflows/build-release.yml)
[![codecov](https://codecov.io/gh/rolschewsky/certbot-dns-hetzner-cloud/graph/badge.svg?token=8RDFM8FWDU)](https://codecov.io/gh/rolschewsky/certbot-dns-hetzner-cloud)

# Certbot DNS Plugin for Hetzner Cloud DNS

This is a Certbot DNS plugin for the new Hetzner Cloud DNS, which allows you to automate the process of obtaining and 
renewing SSL/TLS certificates using the DNS-01 challenge method. This Plugin is not compatible with the old Hetzner DNS 
Console and you might want to take a look at the [certbot-dns-hetzner][1] plugin instead.

## Setup
### Installation
To install the Certbot DNS plugin for Hetzner Cloud DNS, you can either use `pip` or `snap`.

#### Installation using *pip*
If you installed Certbot within a virtual environment (e.g., `/opt/certbot`) as per [official Certbot instructions][2] 
you can install the plugin using the following command:
```bash
/opt/certbot/bin/pip install certbot-dns-hetzner-cloud
```

#### Installation using *snap*
If you installed Certbot using `snap`, you can install the plugin with the following commands:
```bash
sudo snap install certbot-dns-hetzner-cloud
sudo snap set certbot trust-plugin-with-root=ok
sudo snap connect certbot:plugin certbot-dns-hetzner-cloud
```

#### Verify installation
After installation, you can verify that the plugin is available by running:
```bash
certbot plugins
```

you should see `dns-hetzner-cloud` listed among the available plugins.

### Storing the API Token
Create a configuration file under `/etc/letsencrypt/hetzner-cloud.ini` with the following content:
```ini
# Hetzner Cloud API Token
dns_hetzner_cloud_api_token = your_api_token_here
```

Make sure to set the correct permissions for the configuration file to protect your API token:
```bash
sudo chmod 600 /etc/letsencrypt/hetzner_cloud.ini
```

If you want to use a different path for the configuration file, you can specify it using the `--dns-hetzner-cloud-credentials` option when running Certbot.

The token must belong to the Hetzner Cloud project that contains the zone. The plugin looks up the zones of that 
project and uses the most specific one the name belongs to, so zones for subdomains work as well.

## Usage
You can use the plugin with Certbot by specifying the `dns-hetzner-cloud` authenticator. 
Here is an example command to obtain a certificate for a wildcard subdomain:
```bash
certbot certonly --agree-tos \
  --authenticator dns-hetzner-cloud \
  -d '*.example.eu'
```

If you want to use a different path for the configuration file, you can specify it using the  
`--dns-hetzner-cloud-credentials` option.
```bash
certbot certonly --agree-tos \
  --authenticator dns-hetzner-cloud \
  --dns-hetzner-cloud-credentials /path/to/your/hetzner_cloud.ini \
  -d '*.example.eu'
```

## Options
The following options can be given on the command line or in the credentials file:

| Command line                                  | Credentials file                               | Default |
|-----------------------------------------------|------------------------------------------------|---------|
| `--dns-hetzner-cloud-propagation-seconds 120` | `dns_hetzner_cloud_propagation_seconds = 120` | `30`    |
| `--dns-hetzner-cloud-follow-cname`            | `dns_hetzner_cloud_follow_cname = true`        | off     |

A value on the command line (or in Certbot's `cli.ini`) takes precedence over the credentials file. Certbot stores 
command line values for renewal, so they keep winning on every renewal of that certificate. Values in the credentials 
file are read on every run, so changing the file takes effect on the next renewal.

### Propagation seconds
The number of seconds the plugin waits after creating the TXT record before Let's Encrypt checks it. Raise it if 
validation fails with "No TXT record found".

### Follow CNAME
With this option the plugin resolves `_acme-challenge.<domain>` before creating the TXT record. If it is a CNAME, the 
record is created in the zone the CNAME points to. This lets you keep the API token away from your main zone:

1. Create a separate zone, e.g. `acme-example.eu`, in its own Hetzner Cloud project and create the API token there.
2. Add a CNAME once per name in your main zone, e.g. `_acme-challenge.example.eu` → `example-eu.acme-example.eu`.
3. Enable the option. For `*.example.eu` the plugin then creates the TXT record `example-eu` in `acme-example.eu`.

The token can only change the separate zone. The CNAME is resolved with the system resolver; names without a CNAME 
are handled as before.

[1]:https://github.com/ctrlaltcoop/certbot-dns-hetzner
[2]:https://certbot.eff.org/instructions
