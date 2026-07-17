"""The Energy Insights Monitor integration.

YAML-configured (no config flow): reads an `energy_insights_monitor:` block with shared
`defaults` and a `devices` list, then creates, per device, the family of derived
and cumulative sensors that the old `scripts/energy_monitor` generator used to
render into static packages.

Cumulative/cycle sensors reuse the Lean core (see `lean.py`), so history is
consolidated to one LTS row per cycle instead of thousands. Hard dependency on
`lean_utility_meter` is declared in the manifest.
"""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.discovery import async_load_platform

from .const import DOMAIN, CONF_DEFAULTS, CONF_DEVICES
from .schema import CONFIG_SCHEMA  # noqa: F401  (exported for HA config validation)
from .device import build_device_config

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Energy Insights Monitor from YAML."""
    conf = config.get(DOMAIN)
    if not conf:
        return True

    defaults = conf.get(CONF_DEFAULTS, {})
    devices = conf.get(CONF_DEVICES, [])

    # Resolve each device against the shared defaults into a fully-expanded spec.
    device_configs = [build_device_config(dev, defaults) for dev in devices]
    _LOGGER.info("Energy Insights Monitor: setting up %d device(s)", len(device_configs))

    # hass_config is kept for the nested discovery dispatch to lean_utility_meter
    # (async_load_platform requires the full config for component bootstrap).
    hass.data[DOMAIN] = {"devices": device_configs, "hass_config": config}

    # Forward the resolved specs to each platform, which instantiates the per-family
    # entities for every device (sensors for the meters, binary_sensors for run state).
    for platform in PLATFORMS:
        hass.async_create_task(
            async_load_platform(hass, platform, DOMAIN, {"devices": device_configs}, config)
        )

    # TODO: register reload service (energy_insights_monitor.reload) so devices can be
    #       added/edited without a full HA restart.
    return True
