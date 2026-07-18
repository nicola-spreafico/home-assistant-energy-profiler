"""Instantaneous cost-rate estimates (part of the ``cost`` family).

Reincarnates ``001_basics/basics_004_[energy_cost_instant]``: from the current
power draw and price, the projected cost if that draw held for an hour / day /
month / year. Purely instantaneous (measurement), recomputed on power/price change.
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
        factor: float, unit: str, name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_native_unit_of_measurement = unit
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


# (name_suffix, unit, hours factor)
INSTANT_COST_VARIANTS = (
    ("hourly", "€/h", 1),
    ("daily", "€/d", 24),
    ("monthly", "€/m", 24 * 30),
    ("yearly", "€/y", 24 * 365),
)
