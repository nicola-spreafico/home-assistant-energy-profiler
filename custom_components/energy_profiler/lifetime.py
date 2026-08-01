"""Energy lifetime accumulator — the device's decoupled all-time total.

Reincarnates the generator's ``_energy_lifetime`` (basics_002), created there so the
all-time number would "not be dependent on the source sensor that may change during
time (new smart plug, change of energy id)". Here it is promoted to the **single
source** every downstream family reads from (energy cycle meters, cost integrator,
self/grid balancer): it accumulates only the *positive* increments of the hardware
energy sensor and skips resets, so a plug swap or a sensor-id change never resets the
number and never injects a phantom delta into any downstream sensor.

Kept as a RestoreSensor (like the cost/split accumulators) for consistency and to
avoid coupling to core ``utility_meter`` constructor internals.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import logging

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
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


class EnergyLifetimeSensor(RestoreSensor):
    """All-time kWh total: accumulates the positive deltas of the hw energy source."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        energy_source: str,
        icon: str = "mdi:counter",
        name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._energy_source = energy_source
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

    async def async_reset(self) -> None:
        """Zero the all-time total (reset entity service)."""
        self._total = Decimal(0)
        self.async_write_ha_state()

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
        # Skip resets / no-change; never subtract. A large delta after downtime is
        # real energy and is intentionally kept (matches the old utility_meter, which
        # did not cap) — the per-event spike guards live in the cost/split consumers.
        if diff <= 0:
            return

        self._total += Decimal(str(diff))
        self.async_write_ha_state()


class GatedEnergyAccumulator(EnergyLifetimeSensor):
    """Energy accumulated only while a gatekeeper is on.

    The base of the running/standby energy groups (generalizes the original
    ``004_standby/standby_002``): sources the decoupled lifetime's deltas and adds
    them only while ``gate_entity`` (a ``_running`` or ``_standby`` binary sensor)
    is on. While the gatekeeper is off (or unavailable) the baseline is advanced
    but nothing is added, so out-of-gate energy is never counted.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        energy_source: str,
        gate_entity: str,
        icon: str = "mdi:power-sleep",
        name: str | None = None,
    ) -> None:
        super().__init__(hass, slug=slug, energy_source=energy_source, icon=icon, name=name)
        self._gate_entity = gate_entity

    @callback
    def _async_on_energy_change(self, event: Event) -> None:
        if not self.hass.states.is_state(self._gate_entity, STATE_ON):
            # Gate closed (or gatekeeper unavailable): keep the baseline current
            # so this energy is excluded, but do not accumulate.
            new_state = event.data.get("new_state")
            value = _to_float(new_state.state if new_state else None)
            if value is not None:
                self._last_energy = value
            return
        super()._async_on_energy_change(event)
