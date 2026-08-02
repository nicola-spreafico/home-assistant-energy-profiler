"""Instantaneous power sensors (family ``power``).

Reincarnates ``001_basics/basics_001_[power]`` and ``002_selfsufficiency/
selfsufficiency_001_[power]``:

- :class:`PowerMaxSensor` — the running maximum of the hardware power sensor
  (peak draw), reset on demand.
- :class:`PowerSplitSensor` — the instantaneous grid / self / solar / battery
  split of power, from the same house flows the energy split uses (flows.py).
  Being instantaneous rather than accumulated, each portion is a plain product
  of ``P`` and its fraction, so no remainder trick is needed here.
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_FLOW_GRID, CONF_FLOW_SOLAR, FLOW_CHANNELS
from .flows import read_weights, self_fraction, solar_fraction_of_self, source_entities

_LOGGER = logging.getLogger(__name__)

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class PowerMaxSensor(RestoreSensor):
    """Running peak of the hardware power sensor (W), restored across restarts."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"

    def __init__(
        self, hass: HomeAssistant, *, slug: str, power_source: str,
        icon: str = "mdi:flash-outline", name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._power_source = power_source
        self._max: float = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and (v := _to_float(last.native_value)) is not None:
            self._max = v
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._power_source], self._on_power)
        )

    @property
    def native_value(self) -> float:
        return self._max

    async def async_reset(self) -> None:
        """Zero the peak (reset entity service)."""
        self._max = 0.0
        self.async_write_ha_state()

    @callback
    def reset(self) -> None:
        """Reset the peak (used by the reset service)."""
        self._max = 0.0
        self.async_write_ha_state()

    @callback
    def _on_power(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        current = _to_float(new_state.state if new_state else None)
        if current is not None and current > self._max:
            self._max = current
            self.async_write_ha_state()


class PowerSplitSensor(SensorEntity):
    """One portion of the instantaneous power draw: ``P * fraction``.

    ``portion`` selects which fraction, all read from the same house flows:
    ``grid`` and ``self`` are complements of each other, ``solar`` and
    ``battery`` subdivide ``self``. With a single channel configured that
    channel *is* the self share, so its fraction is the self fraction.

    Unlike the energy splitter, unreadable flows make this sensor unavailable
    rather than defaulting to all-grid: there is no delta here that has to be
    attributed to something, so saying nothing beats saying zero.
    """

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"

    def __init__(
        self, hass: HomeAssistant, *, slug: str, power_source: str, flows: dict,
        portion: str, icon: str, name: str | None = None,
    ) -> None:
        if portion not in (CONF_FLOW_GRID, "self", *FLOW_CHANNELS):
            raise ValueError(portion)
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._power_source = power_source
        self._flows = flows
        self._portion = portion
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._power_source, *source_entities(self._flows)],
                self._on_change,
            )
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    def _factor(self, weights: dict[str, float]) -> float:
        frac_self = self_fraction(weights)
        if self._portion == "self":
            return frac_self
        if self._portion == CONF_FLOW_GRID:
            return 1 - frac_self
        # A channel: its share of self, or the whole of it when it is the only one.
        if len(self._flows["channels"]) < 2:
            return frac_self
        frac_solar = solar_fraction_of_self(weights)
        return frac_self * (frac_solar if self._portion == CONF_FLOW_SOLAR else 1 - frac_solar)

    @callback
    def _recalculate(self) -> None:
        power = _to_float((s := self.hass.states.get(self._power_source)) and s.state)
        weights = read_weights(self.hass, self._flows)
        if power is None or weights is None:
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        self._attr_native_value = round(power * self._factor(weights), 6)
