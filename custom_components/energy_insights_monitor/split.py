"""Self-production vs. grid split, in native Python.

Reincarnates the generator's ``002_selfsufficiency`` live sources:

- ``EnergySplitAccumulatorSensor`` (fragment 002): on each hardware energy tick,
  split the delta by the instantaneous self-sufficiency percentage and accumulate
  either the self-produced or the grid-imported portion. Two instances (self, grid)
  driven by the same energy source stay consistent because they read the same
  percentage at the same event.
- ``SelfSufficiencyRatioSensor`` (fragment 007): the live self-sufficiency % for a
  cycle, ``from_self / total * 100``, computed straight from the two Lean cycle
  meters (no transient meters exist in the new design).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
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

# Energy deltas above this (kWh) are treated as meter resets / spikes and skipped.
# Matches the old energy-balancer guard ``0 < diff < 5`` (tighter than the cost one).
DEFAULT_MAX_DELTA = 5.0

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class EnergySplitAccumulatorSensor(RestoreSensor):
    """Accumulate the self-produced or grid-imported portion of consumed energy."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "kWh"

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        energy_source: str,
        ratio_source: str,
        portion: str,
        icon: str,
        max_delta: float = DEFAULT_MAX_DELTA,
        name: str | None = None,
    ) -> None:
        if portion not in ("self", "grid"):
            raise ValueError(f"portion must be 'self' or 'grid', got {portion!r}")
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._energy_source = energy_source
        self._ratio_source = ratio_source
        self._portion = portion
        self._max_delta = max_delta
        self._total = Decimal(0)
        self._last_energy: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._total = Decimal(str(last.native_value))
            except (InvalidOperation, ValueError):
                self._total = Decimal(0)

        state = self.hass.states.get(self._energy_source)
        self._last_energy = _to_float(state.state if state else None)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._energy_source], self._async_on_energy_change
            )
        )

    @property
    def native_value(self) -> Decimal:
        return self._total

    @callback
    def _async_on_energy_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        new_energy = _to_float(new_state.state if new_state else None)
        if new_energy is None:
            return

        previous = self._last_energy
        self._last_energy = new_energy
        if previous is None:
            return

        diff = new_energy - previous
        if not (0 < diff < self._max_delta):
            return

        # Percentage unavailable -> assume worst case (all from grid), matching the
        # old template's float(0) default on the ratio source.
        raw_pct = _to_float(
            (rs := self.hass.states.get(self._ratio_source)) and rs.state
        )
        pct_self = max(0.0, min(100.0, raw_pct if raw_pct is not None else 0.0))

        self_portion = Decimal(str(diff)) * Decimal(str(pct_self)) / Decimal(100)
        portion = self_portion if self._portion == "self" else Decimal(str(diff)) - self_portion

        self._total += portion
        self.async_write_ha_state()


class SelfSufficiencyRatioSensor(SensorEntity):
    """Live self-sufficiency % for a cycle: from_self / total * 100."""

    _attr_should_poll = False
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        numerator: str,
        denominator: str,
        icon: str = "mdi:solar-power-variant",
        name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._numerator = numerator
        self._denominator = denominator
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._numerator, self._denominator], self._async_on_change
            )
        )

    @callback
    def _async_on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        total = _to_float((s := self.hass.states.get(self._denominator)) and s.state)
        produced = _to_float((s := self.hass.states.get(self._numerator)) and s.state)
        # No consumption in the cycle -> undefined (avoid div-by-zero and skewing LTS).
        if total is None or produced is None or total <= 0:
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        self._attr_native_value = round((produced / total) * 100, 6)
