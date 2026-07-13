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
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from datetime import timedelta

from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)

# Fired on each completed cycle so users can automate notifications themselves
# (the HA-idiomatic alternative to the old package's built-in notify action).
EVENT_CYCLE_COMPLETED = "energy_insights_monitor_cycle_completed"
# Fired instead when a closed cycle fails the configured min/max limits.
EVENT_CYCLE_DISCARDED = "energy_insights_monitor_cycle_discarded"


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

    async def async_reset(self) -> None:
        """Zero the accumulated value (reset entity service)."""
        self._value = Decimal(0)
        self.async_write_ha_state()


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
    the corresponding per-cycle mean. state_class TOTAL (not total_increasing) so it
    is valid for monetary device classes too.
    """

    _attr_state_class = SensorStateClass.TOTAL

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


class ScaledRatioSensor(SensorEntity):
    """``numerator / denominator * scale`` (e.g. cost per hour: €total / s * 3600)."""

    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, hass: HomeAssistant, *, slug: str, numerator: str, denominator: str,
        scale: float, unit: str, icon: str, name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._num = numerator
        self._den = denominator
        self._scale = scale
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._num, self._den], self._on_change)
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        num = _to_float((s := self.hass.states.get(self._num)) and s.state)
        den = _to_float((s := self.hass.states.get(self._den)) and s.state)
        if num is None or den is None or den <= 0:
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        self._attr_native_value = round(num / den * self._scale, 3)


class HumanDurationSensor(SensorEntity):
    """A human-readable formatting of a seconds-valued source (``2h 05m``)."""

    _attr_should_poll = False
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self, hass: HomeAssistant, *, slug: str, seconds_source: str, name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._source = seconds_source
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._source], self._on_change)
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        secs = _to_float((s := self.hass.states.get(self._source)) and s.state)
        if secs is None:
            self._attr_native_value = None
            return
        total = int(secs)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        self._attr_native_value = f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


class CompletedValueSensor(_RestoreDecimal):
    """The last completed cycle's value (energy or duration), updated on cycle end."""

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


class CycleSnapshotSensor(SensorEntity):
    """Timestamp of a cycle boundary, carrying the lifetimes at that instant as attrs.

    Reincarnates cycle_start_snapshot / cycle_stop_snapshot (cycles_002): the start
    snapshot exposes ``initial_*`` attributes, the stop snapshot ``final_*`` — read
    by the live and standby logic to bound a cycle.
    """

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, hass: HomeAssistant, *, slug: str, icon: str, name: str | None = None) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    @callback
    def set_snapshot(self, when, attributes: dict) -> None:
        self._attr_native_value = when
        self._attr_extra_state_attributes = attributes
        self.async_write_ha_state()


class CycleValidationSensor(SensorEntity):
    """Whether the last completed cycle passed the configured min/max limits."""

    _attr_should_poll = False
    _attr_icon = "mdi:check-decagram"

    def __init__(self, hass: HomeAssistant, *, slug: str, name: str | None = None) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_native_value = None

    @callback
    def set(self, status: str) -> None:
        self._attr_native_value = status
        self.async_write_ha_state()


class CycleLiveSensor(SensorEntity):
    """During a running cycle: ``current(source) - initial(start snapshot)``, else 0."""

    _attr_should_poll = False

    def __init__(
        self, hass: HomeAssistant, *, slug: str, source_entity: str, snapshot_entity: str,
        initial_attr: str, running_entity: str, unit: str,
        device_class: SensorDeviceClass | None, icon: str, name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._source = source_entity
        self._snapshot = snapshot_entity
        self._initial_attr = initial_attr
        self._running = running_entity
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source, self._snapshot, self._running], self._on_change
            )
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        if not self.hass.states.is_state(self._running, STATE_ON):
            self._attr_native_value = 0.0
            return
        current = _to_float((s := self.hass.states.get(self._source)) and s.state)
        snap = self.hass.states.get(self._snapshot)
        initial = _to_float(snap and snap.attributes.get(self._initial_attr))
        self._attr_native_value = (
            round(max(0.0, current - initial), 6)
            if current is not None and initial is not None
            else None
        )


class CycleLiveDurationSensor(SensorEntity):
    """Elapsed time of the current running cycle (seconds); 0 when idle."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "s"

    def __init__(
        self, hass: HomeAssistant, *, slug: str, start_snapshot: str, running_entity: str,
        icon: str = "mdi:timer-play-outline", name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._snapshot = start_snapshot
        self._running = running_entity
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._running, self._snapshot], self._on_change
            )
        )
        # Tick while running so the elapsed time advances without other events.
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=10))
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _tick(self, _now) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        if not self.hass.states.is_state(self._running, STATE_ON):
            self._attr_native_value = 0.0
            return
        snap = self.hass.states.get(self._snapshot)
        start = dt_util.parse_datetime(snap.state) if snap else None
        self._attr_native_value = (
            round(max(0.0, (dt_util.utcnow() - start).total_seconds()), 1) if start else 0.0
        )


class StandbyDurationSensor(SensorEntity):
    """Time the device has been idle since it last stopped (s); 0 while running.

    Reincarnates ``004_standby/standby_001_[live]``.
    """

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "s"
    _attr_icon = "mdi:power-sleep"

    def __init__(self, hass: HomeAssistant, *, slug: str, running_entity: str, name: str | None = None) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._running = running_entity
        self._off_since = None
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self.hass.states.is_state(self._running, STATE_ON):
            self._off_since = dt_util.utcnow()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._running], self._on_running)
        )
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=10))
        )

    @callback
    def _on_running(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        self._off_since = None if new_state.state == STATE_ON else dt_util.utcnow()
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _tick(self, _now) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        if self._off_since is None or self.hass.states.is_state(self._running, STATE_ON):
            self._attr_native_value = 0.0
            return
        self._attr_native_value = round(max(0.0, (dt_util.utcnow() - self._off_since).total_seconds()), 1)


def _validate(duration_s: float, energy: float | None, limits: dict) -> tuple[bool, str]:
    """Check a completed cycle against the configured min/max duration/energy limits."""
    min_d, max_d = limits.get("min_duration"), limits.get("max_duration")
    min_e, max_e = limits.get("min_energy"), limits.get("max_energy")
    if min_d is not None and duration_s < min_d.total_seconds():
        return False, "too_short"
    if max_d is not None and duration_s > max_d.total_seconds():
        return False, "too_long"
    if energy is not None and min_e is not None and energy < min_e:
        return False, "too_little_energy"
    if energy is not None and max_e is not None and energy > max_e:
        return False, "too_much_energy"
    return True, "valid"


class CycleTrackerSensor(_RestoreDecimal):
    """Counts valid completed cycles and drives every cycle sensor.

    On ``_running`` off->on it opens a cycle (snapshotting each metric's lifetime and
    the start timestamp); on on->off it closes it: computes each metric's delta and
    the duration, writes the completed/snapshot/validation sensors, and — if the
    cycle passes the limits — increments the count and feeds the mean accumulators.
    Metrics are ``(name, source_entity, completed_sensor, accumulator_or_None)``.
    """

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        device_prefix: str,
        running_entity: str,
        metrics: list,
        duration_accumulator: DurationAccumulatorSensor,
        completed_duration: CompletedValueSensor,
        start_snapshot: CycleSnapshotSensor,
        stop_snapshot: CycleSnapshotSensor,
        validation: CycleValidationSensor,
        limits: dict | None = None,
        on_delay=None,
        off_delay=None,
        completed_self_sufficiency: CompletedValueSensor | None = None,
        completed_costovertime: CompletedValueSensor | None = None,
        icon: str = "mdi:counter",
        name: str | None = None,
    ) -> None:
        super().__init__(hass, slug=slug, icon=icon, name=name)
        self._device_prefix = device_prefix
        self._running_entity = running_entity
        self._metrics = metrics  # list of (name, source, completed_sensor, acc|None)
        self._duration_acc = duration_accumulator
        self._completed_duration = completed_duration
        self._start_snapshot = start_snapshot
        self._stop_snapshot = stop_snapshot
        self._validation = validation
        self._limits = limits or {}
        self._on_delay = on_delay
        self._off_delay = off_delay
        self._completed_ss = completed_self_sufficiency
        self._completed_cot = completed_costovertime
        self._start_time = None
        self._start: dict[str, float | None] = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._running_entity], self._on_running_change
            )
        )

    @callback
    def _value_of(self, entity_id: str) -> float | None:
        return _to_float((s := self.hass.states.get(entity_id)) and s.state)

    @callback
    def _on_running_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return
        old_off = old_state is not None and old_state.state == STATE_OFF
        old_on = old_state is not None and old_state.state == STATE_ON

        # Only genuine off<->on transitions open/close a cycle. Ignoring
        # unknown/unavailable edges avoids opening a spurious cycle at restart
        # while the device is already running (and the crash of touching the
        # snapshot before it is registered).
        if new_state.state == STATE_ON and old_off:
            self._open_cycle()
        elif new_state.state == STATE_OFF and old_on and self._start_time is not None:
            self._close_cycle()

    @callback
    def _open_cycle(self) -> None:
        now = dt_util.utcnow()
        self._start_time = now - self._on_delay if self._on_delay else now
        self._start = {name: self._value_of(src) for name, src, *_ in self._metrics}
        self._start_snapshot.set_snapshot(
            self._start_time, {f"initial_{name}": self._start[name] for name, *_ in self._metrics}
        )

    @callback
    def _close_cycle(self) -> None:
        now = dt_util.utcnow()
        stop_time = now - self._off_delay if self._off_delay else now
        duration_s = max(0.0, (stop_time - self._start_time).total_seconds())
        self._start_time = None

        deltas: dict[str, float] = {}
        finals: dict[str, float | None] = {}
        for name, src, completed, _acc in self._metrics:
            cur = self._value_of(src)
            finals[name] = cur
            start = self._start.get(name)
            delta = max(0.0, cur - start) if cur is not None and start is not None else 0.0
            deltas[name] = delta
            completed.set(Decimal(str(delta)))

        energy = deltas.get("energy")
        valid, status = _validate(duration_s, energy, self._limits)

        # Snapshots, duration and derived completed values (always written).
        self._stop_snapshot.set_snapshot(stop_time, {f"final_{name}": finals[name] for name in finals})
        self._completed_duration.set(Decimal(str(duration_s)))
        if self._completed_ss is not None and energy and "from_self" in deltas:
            self._completed_ss.set(Decimal(str(round(deltas["from_self"] / energy * 100, 3))))
        if self._completed_cot is not None and "cost" in deltas and duration_s > 0:
            self._completed_cot.set(Decimal(str(round(deltas["cost"] / (duration_s / 3600), 3))))
        self._validation.set(status)

        if valid:
            self._value += Decimal(1)
            self.async_write_ha_state()
            self._duration_acc.add(Decimal(str(duration_s)))
            for name, _src, _completed, acc in self._metrics:
                if acc is not None:
                    acc.add(Decimal(str(deltas[name])))
            event_name = EVENT_CYCLE_COMPLETED
        else:
            event_name = EVENT_CYCLE_DISCARDED

        self.hass.bus.async_fire(
            event_name,
            {
                "device": self._device_prefix,
                "energy_kwh": energy,
                "duration_s": duration_s,
                "status": status,
                "cycle_count": int(self._value),
            },
        )
