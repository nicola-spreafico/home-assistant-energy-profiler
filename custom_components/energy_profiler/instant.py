"""Instantaneous cost-rate estimates (part of the ``cost`` family).

Reincarnates ``001_basics/basics_004_[energy_cost_instant]``: from the current
power draw and price, the projected cost if that draw held for an hour / day /
month / year. Purely instantaneous (measurement), recomputed on power/price change.

The same sensor serves two readings, told apart by which power entity it is fed:
the raw power sensor prices the *whole* draw at the import tariff (ignoring
self-production), while ``<p>_power_from_grid`` prices only the share actually
imported. Both are built for the total group — see ``energy_stack.build_stack``.
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class InstantCostSensor(SensorEntity):
    """Projected cost rate = ``(power/1000) * price * hours_factor`` (€/h, €/d, ...)."""

    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:currency-eur"

    def __init__(
        self, hass: HomeAssistant, *, slug: str, power_source: str, price_source: str,
        factor: float, unit: str, icon: str | None = None, name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_native_unit_of_measurement = unit
        if icon:
            self._attr_icon = icon
        self._power_source = power_source
        self._price_source = price_source
        self._factor = factor
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._power_source, self._price_source], self._on_change
            )
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        power = _to_float((s := self.hass.states.get(self._power_source)) and s.state)
        price = _to_float((s := self.hass.states.get(self._price_source)) and s.state)
        if power is None or price is None:
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        self._attr_native_value = round((power / 1000) * price * self._factor, 3)


# period -> (unit, hours in that period). The factor turns the €/h rate into € per
# period: a pure change of unit, not an accumulation window. Keyed by the same names
# as the Lean cycles (``lean.SUPPORTED_PERIODS``) so a device's ``periods:`` can drive
# these directly. Month and quarter use the same nominal 30/90-day lengths the rest
# of the cost family projects with.
INSTANT_COST_PERIODS = {
    "hourly": ("€/h", 1),
    "daily": ("€/d", 24),
    "weekly": ("€/w", 24 * 7),
    "monthly": ("€/m", 24 * 30),
    "bimonthly": ("€/2m", 24 * 60),
    "quarterly": ("€/q", 24 * 90),
    "yearly": ("€/y", 24 * 365),
}


def resolve_instant_periods(device) -> list[str]:
    """Which projection variants to build for a device.

    ``instant_periods:`` when the user set it (``[]`` switches the projections off
    entirely), otherwise the device's ``periods:`` — so by default the projections
    line up with the period meters instead of being a fixed set of four.
    """
    from .const import CONF_INSTANT_PERIODS, CONF_PERIODS, DEFAULT_PERIODS

    requested = device.get(CONF_INSTANT_PERIODS)
    if requested is None:
        requested = device.get(CONF_PERIODS) or DEFAULT_PERIODS

    resolved: list[str] = []
    for period in requested:
        if period not in INSTANT_COST_PERIODS:
            _LOGGER.warning(
                "Skipping unsupported instant period %r for %s",
                period,
                device.get("prefix"),
            )
            continue
        resolved.append(period)
    return resolved
