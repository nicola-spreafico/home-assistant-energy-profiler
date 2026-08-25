"""Binary sensor platform — the running and standby gatekeepers.

``_running`` (reincarnates ``003_cycles/cycles_001_[running]``) drives the cycle
tracking; ``_standby`` drives the standby family. Both come in flavors chosen by
the device's ``run`` / ``standby`` blocks:

- power threshold with debounce (``trigger: power``): the native
  ``numeric_state ... for:`` semantics, in Python. Running compares upward
  (on above / off below); standby compares downward (on below / off above);
- template (``trigger: template``): ``state`` (and optional ``available``) templates;
- ``standby: true`` (default flavor): standby is simply "running is off",
  mirroring the ``_running`` sensor.

State is restored across restarts (like the original's reload-preserving template).
"""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    TrackTemplate,
    async_call_later,
    async_track_state_change_event,
    async_track_template_result,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import result_as_boolean

from . import families
from .const import DOMAIN
from .device import entity_label, family_device_info_for

_LOGGER = logging.getLogger(__name__)

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def async_setup_entry(hass, entry, async_add_entities):
    """Build the binary sensors for every resolved device."""
    entities = []
    for device in hass.data[DOMAIN].get("devices", []):
        prefix = device["prefix"]
        for family, family_entities in families.build_binary_sensor_groups(
            hass, device
        ).items():
            info = family_device_info_for(device, family)
            for entity in family_entities:
                entity._attr_device_info = info
                entity._attr_has_entity_name = True
                entity._attr_name = entity_label(
                    entity.entity_id.split(".", 1)[1], prefix
                )
                entities.append(entity)
    async_add_entities(entities)


class _RunningBase(BinarySensorEntity, RestoreEntity):
    """Shared running-sensor behavior: device_class + state restore + icon."""

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, hass: HomeAssistant, *, slug: str, name: str | None = None) -> None:
        self.hass = hass
        self.entity_id = f"binary_sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_is_on = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in (STATE_ON, "off"):
            self._attr_is_on = last.state == STATE_ON

    @property
    def icon(self) -> str:
        return "mdi:power" if self._attr_is_on else "mdi:power-off"


class _StandbyPresentation:
    """Presentation for the standby sensors: no device class, sleep icons."""

    _attr_device_class = None

    @property
    def icon(self) -> str:
        return "mdi:power-sleep" if self._attr_is_on else "mdi:power"


class _DebouncedPowerBase(_RunningBase):
    """Power-threshold gatekeeper with `for:`-style debounce on both edges.

    Subclasses define the comparison direction via `_want_on` / `_want_off`.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        power_source: str,
        on_delay,
        off_delay,
        name: str | None = None,
    ) -> None:
        super().__init__(hass, slug=slug, name=name)
        self._power_source = power_source
        self._on_delay = on_delay
        self._off_delay = off_delay
        self._pending: bool | None = None  # transition being debounced
        self._unsub_timer = None

    def _want_on(self, power: float) -> bool:
        raise NotImplementedError

    def _want_off(self, power: float) -> bool:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._power_source], self._on_power
            )
        )
        state = self.hass.states.get(self._power_source)
        if state is not None:
            self._evaluate(_to_float(state.state))

    @callback
    def _cancel(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        self._pending = None

    @callback
    def _schedule(self, target: bool, delay) -> None:
        self._cancel()
        self._pending = target
        self._unsub_timer = async_call_later(
            self.hass, delay, lambda _now: self._fire(target)
        )

    @callback
    def _fire(self, target: bool) -> None:
        self._unsub_timer = None
        self._pending = None
        if self._attr_is_on is not target:
            self._attr_is_on = target
            self.async_write_ha_state()

    @callback
    def _on_power(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        self._evaluate(_to_float(new_state.state if new_state else None))

    @callback
    def _evaluate(self, power: float | None) -> None:
        if power is None:
            return
        want_on = self._want_on(power)
        want_off = self._want_off(power)

        # Drop a pending transition whose "for" condition no longer holds.
        if self._pending is True and not want_on:
            self._cancel()
        elif self._pending is False and not want_off:
            self._cancel()

        if want_on and self._attr_is_on is not True and self._pending is not True:
            self._schedule(True, self._on_delay)
        elif want_off and self._attr_is_on is not False and self._pending is not False:
            self._schedule(False, self._off_delay)


class PowerRunningBinarySensor(_DebouncedPowerBase):
    """Running when power > on_above for on_delay; idle when < off_below for off_delay."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        power_source: str,
        on_above: float,
        off_below: float,
        on_delay,
        off_delay,
        name: str | None = None,
    ) -> None:
        super().__init__(
            hass, slug=slug, power_source=power_source,
            on_delay=on_delay, off_delay=off_delay, name=name,
        )
        self._on_above = on_above
        self._off_below = off_below

    def _want_on(self, power: float) -> bool:
        return power > self._on_above

    def _want_off(self, power: float) -> bool:
        return power < self._off_below


class PowerStandbyBinarySensor(_StandbyPresentation, _DebouncedPowerBase):
    """Standby when power < on_below for on_delay; over when > off_above for off_delay."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        power_source: str,
        on_below: float,
        off_above: float | None,
        on_delay,
        off_delay,
        name: str | None = None,
    ) -> None:
        super().__init__(
            hass, slug=slug, power_source=power_source,
            on_delay=on_delay, off_delay=off_delay, name=name,
        )
        self._on_below = on_below
        # No explicit hysteresis: exit standby at the same threshold.
        self._off_above = off_above if off_above is not None else on_below

    def _want_on(self, power: float) -> bool:
        return power < self._on_below

    def _want_off(self, power: float) -> bool:
        return power > self._off_above


class StandbyFromRunningBinarySensor(_StandbyPresentation, _RunningBase):
    """Default standby flavor: on exactly while ``_running`` is off.

    Follows the running sensor's availability: while running is unknown or
    unavailable, standby is unavailable too (so no energy gets misattributed).
    """

    def __init__(self, hass: HomeAssistant, *, slug: str, running_entity: str, name: str | None = None) -> None:
        super().__init__(hass, slug=slug, name=name)
        self._running_entity = running_entity

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._running_entity], self._on_running
            )
        )
        self._sync()

    @callback
    def _on_running(self, event: Event) -> None:
        self._sync()
        self.async_write_ha_state()

    @callback
    def _sync(self) -> None:
        state = self.hass.states.get(self._running_entity)
        if state is None or state.state in _INVALID:
            self._attr_available = False
            return
        self._attr_available = True
        self._attr_is_on = state.state != STATE_ON


class TemplateRunningBinarySensor(_RunningBase):
    """Running state (and availability) driven by user templates."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        state_template,
        availability_template=None,
        name: str | None = None,
    ) -> None:
        super().__init__(hass, slug=slug, name=name)
        self._state_tpl = state_template
        self._avail_tpl = availability_template

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        tracks = [TrackTemplate(self._state_tpl, None)]
        if self._avail_tpl is not None:
            tracks.append(TrackTemplate(self._avail_tpl, None))
        info = async_track_template_result(self.hass, tracks, self._on_template)
        self.async_on_remove(info.async_remove)
        info.async_refresh()

    @callback
    def _on_template(self, event, updates) -> None:
        for update in updates:
            if update.template is self._state_tpl:
                self._attr_is_on = result_as_boolean(update.result)
            elif self._avail_tpl is not None and update.template is self._avail_tpl:
                self._attr_available = result_as_boolean(update.result)
        self.async_write_ha_state()


class TemplateStandbyBinarySensor(_StandbyPresentation, TemplateRunningBinarySensor):
    """Standby state (and availability) driven by user templates."""


class BatteryCycleCoverageBinarySensor(BinarySensorEntity):
    """Whether the currently usable battery energy covers one average cycle.

    This is deliberately an estimate based on completed, valid cycles. It does
    not reserve energy, account for concurrent house loads or model inverter
    discharge limits.
    """

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        battery_energy_source: str,
        cycle_energy_source: str,
        cycle_count_source: str,
    ) -> None:
        self.hass = hass
        self.entity_id = f"binary_sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = slug
        self._battery_energy_source = battery_energy_source
        self._cycle_energy_source = cycle_energy_source
        self._cycle_count_source = cycle_count_source
        self._battery_kwh: float | None = None
        self._cycle_kwh: float | None = None
        self._valid_cycles: int | None = None
        self._attr_is_on = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [
                    self._battery_energy_source,
                    self._cycle_energy_source,
                    self._cycle_count_source,
                ],
                self._on_source_change,
            )
        )
        self._recalculate()

    @callback
    def _on_source_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        battery_state = self.hass.states.get(self._battery_energy_source)
        cycle_state = self.hass.states.get(self._cycle_energy_source)
        count_state = self.hass.states.get(self._cycle_count_source)
        battery_kwh = _to_float(battery_state.state if battery_state else None)
        cycle_kwh = _to_float(cycle_state.state if cycle_state else None)
        cycle_count = _to_float(count_state.state if count_state else None)

        if (
            battery_kwh is None
            or battery_kwh < 0
            or cycle_kwh is None
            or cycle_kwh <= 0
            or cycle_count is None
            or cycle_count < 1
        ):
            self._battery_kwh = None
            self._cycle_kwh = None
            self._valid_cycles = None
            self._attr_available = False
            self._attr_is_on = None
            return

        self._battery_kwh = battery_kwh
        self._cycle_kwh = cycle_kwh
        self._valid_cycles = int(cycle_count)
        self._attr_available = True
        self._attr_is_on = battery_kwh >= cycle_kwh

    @property
    def icon(self) -> str:
        if not self._attr_available:
            return "mdi:battery-unknown"
        return "mdi:battery-check" if self._attr_is_on else "mdi:battery-alert"

    @property
    def extra_state_attributes(self) -> dict:
        if not self._attr_available:
            return {
                "battery_energy_source": self._battery_energy_source,
                "cycle_energy_source": self._cycle_energy_source,
                "estimate": "mean_of_valid_cycles",
            }
        return {
            "battery_available_energy_kwh": round(self._battery_kwh, 3),
            "average_cycle_energy_kwh": round(self._cycle_kwh, 3),
            "energy_margin_kwh": round(self._battery_kwh - self._cycle_kwh, 3),
            "average_cycles_covered": round(
                self._battery_kwh / self._cycle_kwh, 2
            ),
            "valid_cycles": self._valid_cycles,
            "battery_energy_source": self._battery_energy_source,
            "cycle_energy_source": self._cycle_energy_source,
            "estimate": "mean_of_valid_cycles",
        }
