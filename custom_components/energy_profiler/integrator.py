"""Incremental cost integrator.

Reincarnates the old generator's ``_energy_cost_lifetime`` trigger-template
(``001_basics/basics_003``): a monotonic € accumulator that, on every energy
tick, adds ``delta_energy * current_price`` to its running total. Integrating on
the *delta* (not the total) means a later price change only affects future
consumption, keeping historical cost accurate.

The running total is the live source that the per-cycle Lean cost meters consume,
so it must survive restarts — hence RestoreSensor. It is deliberately not a
utility_meter: the accumulation is bespoke (price-weighted, spike-guarded).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import logging

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DEFAULT_COST_PRECISION

_LOGGER = logging.getLogger(__name__)

# Ignore energy deltas above this (kWh) — a meter reset or a smart-plug swap shows
# up as a huge jump and must not be priced. Mirrors the old ``0 < diff < 10`` guard.
DEFAULT_MAX_DELTA = 10.0

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    """Parse a state to float, or None if it is not a finite number."""
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class EnergyCostIntegratorSensor(RestoreSensor):
    """A € accumulator: integrates ``delta(energy_source) * price_source``."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "€"

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        energy_source: str,
        price_source: str,
        max_delta: float = DEFAULT_MAX_DELTA,
        icon: str = "mdi:currency-eur",
        name: str | None = None,
        display_precision: int | None = DEFAULT_COST_PRECISION,
    ) -> None:
        self.hass = hass
        # Display only. The running total below is never rounded — rounding it
        # would leak or gain cents over a lifetime of accumulation.
        self._attr_suggested_display_precision = display_precision
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._energy_source = energy_source
        self._price_source = price_source
        self._max_delta = max_delta
        self._total = Decimal(0)
        self._last_energy: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the running total and start tracking the energy source."""
        await super().async_added_to_hass()

        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._total = Decimal(str(last.native_value))
            except (InvalidOperation, ValueError):
                self._total = Decimal(0)

        # Seed the last-energy baseline from the current source so the first tick
        # after startup measures a delta rather than treating the whole reading as one.
        self._last_energy = _to_float(
            (state := self.hass.states.get(self._energy_source)) and state.state
        )

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._energy_source], self._async_on_energy_change
            )
        )

    @property
    def native_value(self) -> Decimal:
        return self._total

    async def async_reset(self) -> None:
        """Zero the accumulated cost (reset entity service)."""
        self._total = Decimal(0)
        self.async_write_ha_state()

    @callback
    def _async_on_energy_change(self, event: Event) -> None:
        """Add the priced delta of the latest energy tick to the running total."""
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
            # Negative (meter reset), zero, or a spike: don't price it.
            return

        price = _to_float(
            (state := self.hass.states.get(self._price_source)) and state.state
        )
        if price is None:
            return

        self._total += Decimal(str(diff)) * Decimal(str(price))
        self.async_write_ha_state()
