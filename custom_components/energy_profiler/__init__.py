"""The Energy Profiler integration.

YAML-configured: reads an `energy_profiler:` block with shared `defaults` and a
`devices` list, then creates, per device, the family of derived and cumulative
sensors that the old `scripts/energy_monitor` generator used to render into
static packages.

The config flow is import-only (see config_flow.py): the YAML stays the single
source of truth, and the entry exists purely so Home Assistant will let the
integration register devices — one per configured device, plus a system device
carrying the house-level readings. Setup therefore happens in two stages:
`async_setup` parses and resolves the YAML, `async_setup_entry` forwards the
resolved specs to the platforms.

Cumulative/cycle sensors reuse the Lean core (see `lean.py`), so history is
consolidated to one LTS row per cycle instead of thousands. Hard dependency on
`lean_utility_meter` is declared in the manifest.
"""

import logging

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, CONF_DEFAULTS, CONF_DEVICES
from .schema import CONFIG_SCHEMA  # noqa: F401  (exported for HA config validation)
from .device import build_device_config

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Resolve the YAML configuration and make sure an entry exists to back it."""
    conf = config.get(DOMAIN)
    if not conf:
        return True

    defaults = conf.get(CONF_DEFAULTS, {})
    devices = conf.get(CONF_DEVICES, [])

    # Resolve each device against the shared defaults into a fully-expanded spec.
    device_configs = [build_device_config(dev, defaults) for dev in devices]
    _LOGGER.info("Energy Profiler: resolved %d device(s) from YAML", len(device_configs))

    hass.data[DOMAIN] = {"devices": device_configs, "defaults": defaults}

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data={}
        )
    )

    # TODO: register reload service (energy_profiler.reload) so devices can be
    #       added/edited without a full HA restart.
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Forward the resolved specs to the platforms, which build the entities."""
    if DOMAIN not in hass.data:
        # The entry outlived its YAML block: leave it visible but empty rather
        # than failing silently, so the cause is obvious in the UI and the log.
        _LOGGER.error(
            "Energy Profiler has a config entry but no 'energy_profiler:' block in "
            "your YAML configuration; no entities will be created. Restore the "
            "block, or delete the integration entry to remove it for good"
        )
        return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the platforms; the resolved YAML stays for the next setup."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
