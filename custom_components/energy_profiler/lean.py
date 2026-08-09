"""Bridge to the Lean Utility Meter core (meter specs).

Cumulative/cycle families (energy, cost, from_grid, ...) reuse Lean's cycle
meters *natively*: instead of subclassing its sensor, this integration builds
meter **specs** (plain dicts) that Lean's public ``meter_from_spec`` turns into
real Lean entities (see sensor.py).

Those meters are added on *this* integration's platform rather than dispatched
to Lean's, because Home Assistant only attaches a device to entities whose
platform has a config entry — and Lean's discovery platform has none, so meters
sent there could never appear on a device page. The trade-off is that Lean's
maintenance services are registered on Lean's platform; sensor.py re-registers
them here so ``thin_history`` & co. keep working on these meters.

The hard `dependencies` entry in the manifest guarantees ``lean_utility_meter``
is set up first.
"""

from collections.abc import Callable
from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

LEAN_DOMAIN = "lean_utility_meter"

# Lean cycles this integration can create. Aligned with lean/period.py.
SUPPORTED_PERIODS = (
    "hourly", "daily", "weekly", "monthly", "bimonthly", "quarterly", "yearly",
)

DEFAULT_LIVE_UPDATE_INTERVAL = timedelta(minutes=5)


def lean_available(hass: HomeAssistant) -> bool:
    """True if the Lean integration is set up (runtime safety net)."""
    return LEAN_DOMAIN in hass.config.components


def build_period_meters(
    hass: HomeAssistant,
    device: dict,
    *,
    source: str | Callable[[str], str],
    name_suffix: str,
    unit: str | None,
    device_class,
    net_consumption: bool = False,
    absolute_values: bool = False,
    display_precision: int | None = None,
    hidden: bool = False,
) -> list[dict]:
    """Return one Lean meter *spec* per requested cycle for a device sub-metric.

    ``name_suffix`` is appended to the device prefix to form the slug/entity_id,
    e.g. prefix ``foo_em`` + suffix ``energy`` + cycle ``daily`` ->
    ``sensor.foo_em_energy_daily``. The sensor platform forwards these specs to
    the lean_utility_meter platform, which instantiates the actual entities.

    ``display_precision`` caps the decimals the meters *show* (None = let the
    device class decide). Meters accumulate at full precision regardless.

    ``source`` is normally one entity every cycle meters. It may instead be a
    callable ``cycle -> entity_id`` for the case where each cycle has its *own*
    source: a period score is the ratio of that period's two accumulators, so
    the daily meter and the monthly one cannot read the same entity.
    """
    prefix = device["prefix"]
    periods = device.get("periods") or ["daily", "monthly", "yearly"]
    live_update_interval = device.get("live_update_interval") or DEFAULT_LIVE_UPDATE_INTERVAL

    specs: list[dict] = []
    for cycle in periods:
        if cycle not in SUPPORTED_PERIODS:
            _LOGGER.warning("Skipping unsupported period %r for %s", cycle, prefix)
            continue
        slug = f"{prefix}_{name_suffix}_{cycle}"
        spec = {
            "source": source(cycle) if callable(source) else source,
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
        # Same convention: an absent key means "inherit", so only pin the
        # precision when the caller asked for one.
        if display_precision is not None:
            spec["suggested_display_precision"] = display_precision
        # Registered and fully working, but kept off the device page: for meters
        # that exist to be a denominator and echo a counter the user already
        # declared. Read by sensor.py, not by Lean.
        if hidden:
            spec["hidden"] = True
        specs.append(spec)
    return specs
