# SMA SpeedWire Integration for Home Assistant  

## About this fork

This fork adds a configurable polling interval between 10 and 300 seconds, with 30 seconds as the default. The interval can be changed directly from the Home Assistant user interface.

This custom integration connects Home Assistant to SMA inverters via the SpeedWire protocol. It provides three entities for use in dashboards and automations:
- Energy production total in kWh
- Energy production today in kWh
- Power production now in kW

Version 0.1.2 also handles missing inverter responses safely, preventing an empty response from causing an update exception.

![add integration to HACS](img/integration.png)
The integration supports a range of SMA inverters. See the [supported inverter list](https://github.com/skurusa/ha_sma_speedwire/blob/main/custom_components/sma_speedwire/sma_speedwire.py#L27).

## Installation
### a) Install with HACS
- Add `https://github.com/skurusa/ha_sma_speedwire` as a custom integration repository in HACS.
![add custom repo to HACS](img/add_hacs_repo.png)
![add repo to HACS](img/add_hacs_repo2.png)
- Install **SMA SpeedWire Integration** from HACS.
![add integration to HACS](img/add_hacs_integration.png)
### b) Manual installation
If you do not use HACS, run the following commands in the Home Assistant Terminal add-on:
```sh
mkdir -p /config/custom_components
wget -O /tmp/ha_sma_speedwire-main.tar.gz https://github.com/skurusa/ha_sma_speedwire/archive/refs/heads/main.tar.gz
tar -xzf /tmp/ha_sma_speedwire-main.tar.gz --strip-components=2 -C /config/custom_components ha_sma_speedwire-main/custom_components/sma_speedwire
rm /tmp/ha_sma_speedwire-main.tar.gz
```
### Restart
Restart Home Assistant after installation.

## Setup
- After installation, open **Settings -> Devices & services -> Add integration** and select **SMA SpeedWire**.
![add integration to HA](img/add_ha_integration.png)

- Enter the inverter IP address and password during setup. The default password is `0000`. Configure a DHCP reservation in your router so the inverter always receives the same IP address.
![add integration to HA](img/setup_integration.png)

## Debugging
Add the following to `configuration.yaml` to enable debug logging. Please include the relevant debug logs when filing an issue.

See the [Home Assistant logger documentation](https://www.home-assistant.io/integrations/logger/) for more information.

```yml
logger:
  default: warning
  logs:
    custom_components.sma_speedwire: debug
```

## Credits
Inspired by [SMAInverter](https://github.com/Rincewind76/SMAInverter).
