"""Cycle tracking: turn ``_running`` edges into countable, measurable cycles.

Reincarnates the cumulative parts of ``003_cycles`` (counter, durations, completed
snapshots). A cycle opens on ``_running`` off->on (record start time + start energy)
and closes on on->off, at which point:

- the total cycle **count** ticks +1 (a ``total_increasing`` source, so the Lean
  cycle meters over it report cycles-per-period);
- the cycle's **duration** is added to a running total (same, duration-per-period);
- the **last completed** cycle's energy and duration are published as snapshots.

Means (energy/duration per cycle over a period) and the completion notification are
derived/event concerns, left for a later pass.
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
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class _RestoreDecimal(RestoreSensor):
    """A RestoreSensor holding a Decimal total, restored across restarts."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, *, slug: str, icon: str, name: str | None = None) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._value = Decimal(0)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._value = Decimal(str(last.native_value))
            except (InvalidOperation, ValueError):
                self._value = Decimal(0)

    @property
    def native_value(self) -> Decimal:
        return self._value


class DurationAccumulatorSensor(_RestoreDecimal):
    """Total run time across all completed cycles (seconds), fed by the tracker."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "s"

    @callback
    def add(self, seconds: Decimal) -> None:
        self._value += seconds
        self.async_write_ha_state()


class CycleEnergyAccumulatorSensor(_RestoreDecimal):
    """Total energy consumed across all completed cycles (kWh), fed by the tracker.

    Only used to derive the per-cycle energy mean; not exposed per-period (the old
    generator tracked cycle energy only through the mean, not as a period meter).
    """

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"

    @callback
    def add(self, kwh: Decimal) -> None:
        self._value += kwh
        self.async_write_ha_state()


class CycleSumAccumulatorSensor(_RestoreDecimal):
    """Total of a per-cycle quantity (e.g. cost €, from_self kWh) over all cycles.

    Fed by the tracker with the per-cycle delta of a lifetime source; used to derive
    the corresponding per-cycle mean.
    """

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        unit: str,
        device_class: SensorDeviceClass | None,
        icon: str,
        name: str | None = None,
    ) -> None:
        super().__init__(hass, slug=slug, icon=icon, name=name)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @callback
    def add(self, delta: Decimal) -> None:
        self._value += delta
        self.async_write_ha_state()


class MeanSensor(SensorEntity):
    """Per-completed-cycle mean: ``total / count`` (None until the first cycle)."""

    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        total_entity: str,
        count_entity: str,
        unit: str,
        device_class: SensorDeviceClass | None,
        icon: str,
        name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._total_entity = total_entity
        self._count_entity = count_entity
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._total_entity, self._count_entity], self._on_change
            )
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        total = _to_float((s := self.hass.states.get(self._total_entity)) and s.state)
        count = _to_float((s := self.hass.states.get(self._count_entity)) and s.state)
        if total is None or count is None or count <= 0:
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        self._attr_native_value = round(total / count, 3)


class CompletedValueSensor(_RestoreDecimal):
    """The last completed cycle's value (energy or duration), updated on cycle end."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        unit: str,
        device_class: SensorDeviceClass | None,
        icon: str,
        name: str | None = None,
    ) -> None:
        super().__init__(hass, slug=slug, icon=icon, name=name)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @callback
    def set(self, value: Decimal) -> None:
        self._value = value
        self.async_write_ha_state()


class CycleTrackerSensor(_RestoreDecimal):
    """Counts completed cycles and drives the duration/completed sensors.

    Primary of the cycle group: subscribes once to ``_running`` and, on each closed
    cycle, updates itself (+1) plus the partner accumulators/snapshots atomically.
    """

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        running_entity: str,
        energy_entity: str,
        duration_accumulator: DurationAccumulatorSensor,
        energy_accumulator: CycleEnergyAccumulatorSensor,
        completed_energy: CompletedValueSensor,
        completed_duration: CompletedValueSensor,
        extra_deltas: list[tuple[str, "CycleSumAccumulatorSensor"]] | None = None,
        icon: str = "mdi:counter",
        name: str | None = None,
    ) -> None:
        super().__init__(hass, slug=slug, icon=icon, name=name)
        self._running_entity = running_entity
        self._energy_entity = energy_entity
        self._duration_acc = duration_accumulator
        self._energy_acc = energy_accumulator
        self._completed_energy = completed_energy
        self._completed_duration = completed_duration
        # (source_entity, accumulator): the per-cycle delta of each source (cost,
        # from_self, from_grid) is accumulated on cycle close, to derive their means.
        self._extra = extra_deltas or []
        self._extra_start: dict[str, float | None] = {}
        self._start_time = None
        self._start_energy: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._running_entity], self._on_running_change
            )
        )

    @callback
    def _energy_now(self) -> float | None:
        return _to_float(
            (s := self.hass.states.get(self._energy_entity)) and s.state
        )

    @callback
    def _on_running_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return
        was_on = old_state is not None and old_state.state == STATE_ON
        is_on = new_state.state == STATE_ON

        if is_on and not was_on:
            # Cycle opens: snapshot the baselines.
            self._start_time = dt_util.utcnow()
            self._start_energy = self._energy_now()
            for source, _acc in self._extra:
                self._extra_start[source] = _to_float(
                    (s := self.hass.states.get(source)) and s.state
                )
        elif was_on and not is_on and self._start_time is not None:
            # Cycle closes: measure and publish.
            duration = Decimal(str((dt_util.utcnow() - self._start_time).total_seconds()))
            end_energy = self._energy_now()
            self._start_time = None

            self._value += Decimal(1)
            self.async_write_ha_state()
            self._duration_acc.add(duration)
            self._completed_duration.set(duration)
            if end_energy is not None and self._start_energy is not None:
                energy = Decimal(str(max(0.0, end_energy - self._start_energy)))
                self._completed_energy.set(energy)
                self._energy_acc.add(energy)
            self._start_energy = None

            # Per-cycle deltas of the extra sources (cost / from_self / from_grid).
            for source, acc in self._extra:
                current = _to_float((s := self.hass.states.get(source)) and s.state)
                start = self._extra_start.get(source)
                if current is not None and start is not None:
                    acc.add(Decimal(str(max(0.0, current - start))))
