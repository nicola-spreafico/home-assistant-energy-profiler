"""Device status label — a presentation-only enum over the gatekeepers.

``sensor.<prefix>_status`` renders the device's state as a single dashboard
label (``running`` / ``standby`` / ``poweroff`` / ``poweron``). It is derived
from the ``_running`` / ``_standby`` binary sensors and is NOT used by any
internal logic — the families keep gating on the binary sensors directly.

Possible states depend on which signals the device configured:

- running + standby: ``running`` > ``standby`` > ``poweroff``
- running only:      ``running`` / ``poweroff``
- standby only:      ``standby`` / ``poweron`` (not in standby = actively drawing)

With the default standby flavor (standby == not running) ``poweroff`` never
occurs — that flavor cannot distinguish idle-drawing from truly off.
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)

STATE_RUNNING = "running"
STATE_STANDBY = "standby"
STATE_POWEROFF = "poweroff"
STATE_POWERON = "poweron"

_ICONS = {
    STATE_RUNNING: "mdi:power",
    STATE_STANDBY: "mdi:power-sleep",
    STATE_POWEROFF: "mdi:power-off",
    STATE_POWERON: "mdi:power-plug",
}


class DeviceStatusSensor(SensorEntity):
    """Textual device status derived from the running/standby gatekeepers."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        running_entity: str | None = None,
        standby_entity: str | None = None,
        name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._running = running_entity
        self._standby = standby_entity

        options = []
        if running_entity:
            options.append(STATE_RUNNING)
        if standby_entity:
            options.append(STATE_STANDBY)
        # The "neither" state: with a running signal the device is plainly off;
        # with only a standby signal, leaving standby means it is actively drawing.
        options.append(STATE_POWEROFF if running_entity else STATE_POWERON)
        self._attr_options = options
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        sources = [e for e in (self._running, self._standby) if e]
        self.async_on_remove(
            async_track_state_change_event(self.hass, sources, self._on_change)
        )
        self._recompute()

    @property
    def icon(self) -> str:
        return _ICONS.get(self._attr_native_value, "mdi:power-settings")

    @callback
    def _on_change(self, event: Event) -> None:
        self._recompute()
        self.async_write_ha_state()

    def _signal(self, entity_id: str | None) -> bool | None:
        """True/False for a readable gatekeeper, None when invalid/unconfigured."""
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state not in (STATE_ON, STATE_OFF):
            return None
        return state.state == STATE_ON

    @callback
    def _recompute(self) -> None:
        running = self._signal(self._running)
        standby = self._signal(self._standby)

        # Strict availability: an unreadable configured signal means the label
        # cannot be trusted — better unavailable than a wrong claim.
        if (self._running and running is None) or (self._standby and standby is None):
            self._attr_available = False
            self._attr_native_value = None
            return

        self._attr_available = True
        if running:
            self._attr_native_value = STATE_RUNNING
        elif standby:
            self._attr_native_value = STATE_STANDBY
        else:
            self._attr_native_value = STATE_POWEROFF if self._running else STATE_POWERON
