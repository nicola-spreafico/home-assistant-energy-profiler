"""Bridge to the Lean Utility Meter core (discovery specs).

Cumulative/cycle families (energy, cost, from_grid, ...) reuse Lean's cycle
meters *natively*: instead of subclassing its sensor, this integration hands
meter **specs** (plain dicts) to the ``lean_utility_meter`` sensor platform via
discovery (see sensor.py). The meters therefore belong to Lean's platform, and
Lean's maintenance services (``thin_history``, ``calibrate``, ...) target them
exactly like YAML-defined meters — no re-registration needed here.

The hard `dependencies` entry in the manifest guarantees ``lean_utility_meter``
is set up first.
"""

from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

LEAN_DOMAIN = "lean_utility_meter"

# Lean cycles this integration can create. Aligned with lean/period.py.
SUPPORTED_CYCLES = (
    "hourly", "daily", "weekly", "monthly", "bimonthly", "quarterly", "yearly",
)

DEFAULT_LIVE_UPDATE_INTERVAL = timedelta(minutes=5)


def lean_available(hass: HomeAssistant) -> bool:
    """True if the Lean integration is set up (runtime safety net)."""
    return LEAN_DOMAIN in hass.config.components


def build_cycle_meters(
    hass: HomeAssistant,
    device: dict,
    *,
    source: str,
    name_suffix: str,
    unit: str | None,
    device_class,
    net_consumption: bool = False,
    absolute_values: bool = False,
) -> list[dict]:
    """Return one Lean meter *spec* per requested cycle for a device sub-metric.

    ``name_suffix`` is appended to the device prefix to form the slug/entity_id,
    e.g. prefix ``foo_em`` + suffix ``energy`` + cycle ``daily`` ->
    ``sensor.foo_em_energy_daily``. The sensor platform forwards these specs to
    the lean_utility_meter platform, which instantiates the actual entities.
    """
    prefix = device["prefix"]
    cycles = device.get("cycles") or ["daily", "monthly", "yearly"]
    live_update_interval = device.get("live_update_interval") or DEFAULT_LIVE_UPDATE_INTERVAL

    specs: list[dict] = []
    for cycle in cycles:
        if cycle not in SUPPORTED_CYCLES:
            _LOGGER.warning("Skipping unsupported cycle %r for %s", cycle, prefix)
            continue
        slug = f"{prefix}_{name_suffix}_{cycle}"
        specs.append(
            {
                "source": source,
                "name": slug,
                "unique_id": slug,
                # Pin the entity_id so it matches the historical snapshot ids
                # exactly (same entity_id -> same LTS series).
                "entity_id": f"sensor.{slug}",
                "cycle": cycle,
                "parent_meter": slug,
                "live_update_interval": live_update_interval,
                "net_consumption": net_consumption,
                "absolute_values": absolute_values,
                "always_available": True,
                "periodically_resetting": True,
                # Force presentation instead of inheriting it from the source
                # entity (the old generator had to pin these via
                # ``homeassistant.customize``); explicit None means "no value".
                "unit_of_measurement": unit,
                "device_class": device_class,
                "state_class": SensorStateClass.TOTAL,
            }
        )
    return specs
