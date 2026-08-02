"""House-level entities: what the flows say about the whole system.

Everything else in this integration is per-appliance. These sensors report the
house readings the attribution is derived from, on their own device, for two
reasons:

- **The derived solar contribution is otherwise invisible.** When ``solar`` is
  computed as ``load - grid - battery``, that number exists only inside the
  splitter. Publishing it lets you chart it, and — more usefully — check it
  against reality: if it goes negative-clamped at noon or stays flat on a sunny
  day, the declared flows are wrong, and every device is being mis-attributed.
- **The house shares are what you want on a dashboard** next to the per-device
  ones, without deriving them again in a template.

These percentages are **instantaneous** — read from the flows at this moment.
The per-device ones divide two accumulators, so over a period they are
energy-weighted. The two answer different questions and will not match: see the
note in the Level 3 documentation.
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_ENERGY_PRICE,
    CONF_FLOW_BATTERY,
    CONF_FLOW_GRID,
    CONF_FLOW_SOLAR,
    CONF_PERIODS,
    CONF_POWER_FLOWS,
    DEFAULT_PERCENTAGE_PRECISION,
    SYSTEM_PREFIX,
)
from .device import entity_label, system_device_info
from .flows import read_weights, resolve_flows, self_fraction, source_entities

_LOGGER = logging.getLogger(__name__)

ICON_SELF = "mdi:solar-panel"
ICON_GRID = "mdi:transmission-tower"
ICON_SOLAR = "mdi:weather-sunny"
ICON_BATTERY = "mdi:home-battery"

_PORTION_ICONS = {
    CONF_FLOW_GRID: ICON_GRID,
    CONF_FLOW_SOLAR: ICON_SOLAR,
    CONF_FLOW_BATTERY: ICON_BATTERY,
}


class _HouseSensor(SensorEntity):
    """Base: recompute whenever any declared flow moves."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, *, slug: str, flows: dict, icon: str) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_has_entity_name = True
        self._attr_name = entity_label(slug, SYSTEM_PREFIX)
        self._attr_icon = icon
        self._attr_device_info = system_device_info()
        self._flows = flows
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, source_entities(self._flows), self._on_change
            )
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        raise NotImplementedError


class HouseFlowPowerSensor(_HouseSensor):
    """One flow's contribution to the house load, in W.

    Only built for the *derived* solar contribution: the flows you declared are
    already entities you own, and echoing them would add nothing.
    """

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"

    def __init__(self, hass: HomeAssistant, *, slug: str, flows: dict, portion: str, icon: str) -> None:
        super().__init__(hass, slug=slug, flows=flows, icon=icon)
        self._portion = portion

    @callback
    def _recalculate(self) -> None:
        weights = read_weights(self.hass, self._flows)
        if weights is None:
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        self._attr_native_value = round(weights.get(self._portion, 0.0), 6)


class HouseSharePercentageSensor(_HouseSensor):
    """One portion's share of the house load, right now, in %."""

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = DEFAULT_PERCENTAGE_PRECISION

    def __init__(self, hass: HomeAssistant, *, slug: str, flows: dict, portion: str | None, icon: str) -> None:
        super().__init__(hass, slug=slug, flows=flows, icon=icon)
        # None means "the self share": everything that is not the grid.
        self._portion = portion

    @callback
    def _recalculate(self) -> None:
        weights = read_weights(self.hass, self._flows)
        if weights is None:
            self._attr_available = False
            self._attr_native_value = None
            return
        total = sum(weights.values())
        if total <= 0:
            # Nothing flowing: a share of nothing is undefined, and publishing 0
            # would read as "no self-production" on the chart.
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        if self._portion is None:
            value = self_fraction(weights) * 100
        else:
            value = weights.get(self._portion, 0.0) / total * 100
        self._attr_native_value = round(value, 6)


class ConfigurationSensor(SensorEntity):
    """Diagnostic: the declared configuration, readable from the UI.

    State is the number of profiled devices; the attributes carry what was
    declared, so "which flows is this actually using?" is answerable without
    opening the YAML.
    """

    _attr_should_poll = False
    _attr_icon = "mdi:file-cog-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, *, slug: str, defaults: dict, devices: list) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_has_entity_name = True
        self._attr_name = entity_label(slug, SYSTEM_PREFIX)
        self._attr_device_info = system_device_info()
        self._defaults = defaults
        self._devices = devices

    @property
    def native_value(self) -> int:
        return len(self._devices)

    @property
    def extra_state_attributes(self) -> dict:
        flows = self._defaults.get(CONF_POWER_FLOWS) or {}
        resolved = resolve_flows(self._defaults)
        return {
            "devices": [device["prefix"] for device in self._devices],
            "energy_price": self._defaults.get(CONF_ENERGY_PRICE),
            "periods": self._defaults.get(CONF_PERIODS),
            "power_flows": dict(flows),
            "self_channels": resolved["channels"] if resolved else [],
            "solar_is_derived": bool(resolved and resolved["derives_solar"]),
        }


def build(hass: HomeAssistant, defaults: dict, devices: list) -> list:
    """Build the house-level entity set from the shared defaults."""
    entities: list = [
        ConfigurationSensor(
            hass, slug=f"{SYSTEM_PREFIX}_configuration", defaults=defaults, devices=devices
        )
    ]

    flows = resolve_flows(defaults)
    if flows is None:
        return entities

    entities += [
        HouseSharePercentageSensor(
            hass, slug=f"{SYSTEM_PREFIX}_from_self_percentage",
            flows=flows, portion=None, icon=ICON_SELF,
        ),
        HouseSharePercentageSensor(
            hass, slug=f"{SYSTEM_PREFIX}_from_grid_percentage",
            flows=flows, portion=CONF_FLOW_GRID, icon=ICON_GRID,
        ),
    ]
    # Per-channel shares only where a channel exists. With a single channel its
    # share equals self-sufficiency, so it would be a second copy of it.
    if len(flows["channels"]) > 1:
        entities += [
            HouseSharePercentageSensor(
                hass, slug=f"{SYSTEM_PREFIX}_from_{channel}_percentage",
                flows=flows, portion=channel, icon=_PORTION_ICONS[channel],
            )
            for channel in flows["channels"]
        ]

    # The derived solar contribution: the one flow nobody else can see.
    #
    # Deliberately not gated on the solar *channel* existing. Whether the
    # per-device entities may be named "solar" is a question about what can
    # honestly be claimed; whether you can see the number the whole attribution
    # runs on is a question about being able to check it. Only the second one
    # matters here, and it is answerable whenever the value is derived at all.
    if flows["derives_solar"]:
        entities.append(
            HouseFlowPowerSensor(
                hass, slug=f"{SYSTEM_PREFIX}_power_from_solar",
                flows=flows, portion=CONF_FLOW_SOLAR, icon=ICON_SOLAR,
            )
        )

    return entities
