"""House-level entities: what the flows say about the whole system.

Everything else in this integration is per-appliance. These sensors expose the
global house readings across the system device and three dedicated score
devices. Only the percentage shares are published from the instantaneous power
flows; derived power values remain internal to the attribution calculation.

These percentages are **instantaneous** — read from the flows at this moment.
The per-device ones divide two accumulators, so over a period they are
energy-weighted. The two answer different questions and will not match: see the
note in the Level 3 documentation.
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_ENERGY_PRICE,
    CONF_BATTERY_AVAILABLE_ENERGY,
    CONF_BATTERY_CHARGE_POWER,
    CONF_SOLCAST_FORECAST,
    CONF_FLOW_BATTERY,
    CONF_FLOW_GRID,
    CONF_FLOW_SOLAR,
    CONF_PERIODS,
    CONF_POWER_FLOWS,
    DEFAULT_PERCENTAGE_PRECISION,
    SYSTEM_PREFIX,
)
from . import house, ranking
from .device import entity_label, system_device_info
from .energy_flows import resolve_energy_flows
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
            "battery_available_energy": self._defaults.get(CONF_BATTERY_AVAILABLE_ENERGY),
            "battery_charge_power": self._defaults.get(CONF_BATTERY_CHARGE_POWER),
            "solcast_forecast": self._defaults.get(CONF_SOLCAST_FORECAST),
            "periods": self._defaults.get(CONF_PERIODS),
            "power_flows": dict(flows),
            "self_channels": resolved["channels"] if resolved else [],
            "solar_is_derived": bool(resolved and resolved["derives_solar"]),
        }


def build_configuration(hass: HomeAssistant, defaults: dict, devices: list) -> list:
    """Build the integration-root diagnostic entity."""
    return [
        ConfigurationSensor(
            hass, slug=f"{SYSTEM_PREFIX}_configuration", defaults=defaults, devices=devices
        )
    ]


_SCORE_PREFIXES = {
    "self_sufficiency": f"{SYSTEM_PREFIX}_self_sufficiency_percentage_",
    "self_consumption": f"{SYSTEM_PREFIX}_self_consumption_percentage_",
    "prosumption": f"{SYSTEM_PREFIX}_prosumption_percentage_",
}


def _split_score_devices(items: list) -> dict[str, list]:
    """Partition global entities by device without changing their identities."""
    groups = {"system": [], **{name: [] for name in _SCORE_PREFIXES}}
    for item in items:
        slug = (
            item.get("unique_id", "")
            if isinstance(item, dict)
            else item.entity_id.split(".", 1)[1]
        )
        target = next(
            (
                name
                for name, prefix in _SCORE_PREFIXES.items()
                if slug.startswith(prefix)
            ),
            "system",
        )
        groups[target].append(item)
    return groups


def build_house_energy(
    hass: HomeAssistant, defaults: dict, devices: list
) -> dict[str, list]:
    """Build and split global house entities between their device pages.

    Every value is a mixed list of Entity objects and Lean meter specs.
    """
    entities: list = []

    # Prosumption: the generation-side scores, plus the baseline and the
    # leaderboard built on it. Independent of `power_flows` — it reads counters,
    # not the instantaneous split — so it is resolved on its own.
    energy_flows = resolve_energy_flows(defaults)
    if energy_flows is not None:
        entities += house.build(hass, defaults, energy_flows)
        entities += ranking.build(hass, house.system_meter_device(defaults), devices)

    flows = resolve_flows(defaults)
    if flows is None:
        return _split_score_devices(entities)

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

    return _split_score_devices(entities)
