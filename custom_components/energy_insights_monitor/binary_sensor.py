"""Binary sensor platform — appliance running/idle detection.

Reincarnates ``003_cycles/cycles_001_[running]``: the ``_running`` gatekeeper that
every cycle/standby feature keys off. Two flavors, chosen by the device's ``run``
block:

- power threshold with debounce (``trigger: power``): on when power stays above
  ``on_above`` for ``on_delay``, off when it stays below ``off_below`` for
  ``off_delay`` — the native ``numeric_state ... for:`` semantics, in Python;
- template (``trigger: template``): ``state`` (and optional ``available``) templates.

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

_LOGGER = logging.getLogger(__name__)

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Build the binary sensors for every resolved device."""
    if not discovery_info:
        return
    entities = []
    for device in discovery_info.get("devices", []):
        entities.extend(families.build_binary_sensors(hass, device))
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


class PowerRunningBinarySensor(_RunningBase):
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
        super().__init__(hass, slug=slug, name=name)
        self._power_source = power_source
        self._on_above = on_above
        self._off_below = off_below
        self._on_delay = on_delay
        self._off_delay = off_delay
        self._pending: bool | None = None  # transition being debounced
        self._unsub_timer = None

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
        want_on = power > self._on_above
        want_off = power < self._off_below

        # Drop a pending transition whose "for" condition no longer holds.
        if self._pending is True and not want_on:
            self._cancel()
        elif self._pending is False and not want_off:
            self._cancel()

        if want_on and self._attr_is_on is not True and self._pending is not True:
            self._schedule(True, self._on_delay)
        elif want_off and self._attr_is_on is not False and self._pending is not False:
            self._schedule(False, self._off_delay)


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
