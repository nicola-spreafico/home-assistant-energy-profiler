"""Instantaneous power sensors (family ``power``).

Reincarnates ``001_basics/basics_001_[power]`` and ``002_selfsufficiency/
selfsufficiency_001_[power]``:

- :class:`PowerMaxSensor` — the running maximum of the hardware power sensor
  (peak draw), reset on demand.
- :class:`PowerSplitSensor` — the instantaneous self / grid split of power. Being
  instantaneous (not accumulated), ``self = P*pct/100`` and ``grid = P*(1-pct/100)``
  already sum to ``P`` exactly, so no remainder trick is needed here.
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
    """Instantaneous self- or grid-sourced power: ``P * pct/100`` or ``P * (1-pct/100)``.

    With a ``share_source``, a second-level portion *inside* the self share:
    ``P * pct/100 * share/100`` (or the share complement) — the instantaneous
    solar vs battery split, mirroring the energy groups' from_solar/from_battery.
    """

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"

    def __init__(
        self, hass: HomeAssistant, *, slug: str, power_source: str, ratio_source: str,
        portion: str, icon: str, share_source: str | None = None,
        share_complement: bool = False, name: str | None = None,
    ) -> None:
        if portion not in ("self", "grid"):
            raise ValueError(portion)
        if share_source is not None and portion != "self":
            raise ValueError("share_source only splits the self portion")
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._power_source = power_source
        self._ratio_source = ratio_source
        self._portion = portion
        # Second-level split inside the self portion (solar vs battery):
        # multiply by share/100, or by its complement for the other side.
        self._share_source = share_source
        self._share_complement = share_complement
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        sources = [self._power_source, self._ratio_source]
        if self._share_source:
            sources.append(self._share_source)
        self.async_on_remove(
            async_track_state_change_event(self.hass, sources, self._on_change)
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        power = _to_float((s := self.hass.states.get(self._power_source)) and s.state)
        raw_pct = _to_float((s := self.hass.states.get(self._ratio_source)) and s.state)
        if power is None or raw_pct is None:
            self._attr_available = False
            self._attr_native_value = None
            return
        pct = max(0.0, min(100.0, raw_pct))
        factor = pct / 100 if self._portion == "self" else 1 - pct / 100
        if self._share_source is not None:
            raw_share = _to_float((s := self.hass.states.get(self._share_source)) and s.state)
            if raw_share is None:
                self._attr_available = False
                self._attr_native_value = None
                return
            share = max(0.0, min(100.0, raw_share)) / 100
            factor *= (1 - share) if self._share_complement else share
        self._attr_available = True
        self._attr_native_value = round(power * factor, 6)
