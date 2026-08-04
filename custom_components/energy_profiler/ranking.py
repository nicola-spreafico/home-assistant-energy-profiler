"""The leaderboard: which appliance used the self-production best, per period.

Ranking devices by their raw self-sufficiency percentage is the obvious idea and
the wrong one, in two ways that both flatter the wrong appliance.

**It ranks schedulability, not behaviour.** A fridge draws around the clock, so
its share of self-production tends by construction to the house average — not
because it behaves badly, but because it cannot behave otherwise. A washing
machine can be moved, so its figure reflects a decision. Putting them in one
column ranks the category of appliance.

**It ignores size.** A 5 W lamp that happens to be on only in daylight scores
100% and tops the table, having moved a few watt-hours. A heat pump at a modest
40% of 8 kWh moved three orders of magnitude more energy off the grid.

So the ranking is built on ``from_self_advantage`` (see scores.py): the kWh a
device captured beyond what it would have captured by drawing at the same times
as the house as a whole. Size and weather are already divided out, it is signed,
and it is additive — which is what makes a leaderboard of it meaningful rather
than merely ordered.

**The residual is a row too.** The advantage is zero-sum across the whole house,
so whatever the profiled devices add up to is exactly minus what everything
unprofiled did. That figure is published alongside the ranking: a large negative
residual says the house's unmeasured baseline runs at night, which is usually
either the next thing to profile or the next thing to fix.
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_NAME, SYSTEM_PREFIX

_LOGGER = logging.getLogger(__name__)

ICON_RANKING = "mdi:trophy-outline"

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class SolarRankingSensor(SensorEntity):
    """Devices ordered by self-production advantage over one period.

    The state is the leader's name, so the entity is readable on its own; the
    ordered table lives in the attributes, which is what a dashboard card
    iterates. Deliberately not a numeric state: there is no long-term series to
    keep here, because each device's own ``_advantage_`` entity already carries
    its history — this is the live view across them.
    """

    _attr_should_poll = False
    _attr_icon = ICON_RANKING

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        cycle: str,
        devices: list[dict],
        house_self: str,
        house_consumption: str,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._cycle = cycle
        self._house_self = house_self
        self._house_consumption = house_consumption
        # (label, advantage, index, percentage, energy) sources per device.
        self._devices = [
            {
                "name": device.get(CONF_NAME, device["prefix"]),
                "prefix": device["prefix"],
                "advantage": f"sensor.{device['prefix']}_energy_from_self_advantage_{cycle}",
                "index": f"sensor.{device['prefix']}_energy_from_self_index_{cycle}",
                "percentage": f"sensor.{device['prefix']}_energy_from_self_percentage_{cycle}",
                "energy": f"sensor.{device['prefix']}_energy_{cycle}",
            }
            for device in devices
        ]
        self._ranking: list[dict] = []
        self._residual: float | None = None
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        sources = [self._house_self, self._house_consumption]
        for device in self._devices:
            sources += [device["advantage"], device["index"],
                        device["percentage"], device["energy"]]
        self.async_on_remove(
            async_track_state_change_event(self.hass, sources, self._on_change)
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        rows: list[dict] = []
        for device in self._devices:
            advantage = _to_float(
                (s := self.hass.states.get(device["advantage"])) and s.state
            )
            if advantage is None:
                # A device with no split configured, or one still starting up:
                # leave it out rather than rank it as a zero it did not earn.
                continue
            rows.append(
                {
                    "device": device["name"],
                    "prefix": device["prefix"],
                    "advantage_kwh": round(advantage, 3),
                    "index": _round_or_none(
                        (s := self.hass.states.get(device["index"])) and s.state, 2
                    ),
                    "from_self_percentage": _round_or_none(
                        (s := self.hass.states.get(device["percentage"])) and s.state, 1
                    ),
                    "energy_kwh": _round_or_none(
                        (s := self.hass.states.get(device["energy"])) and s.state, 3
                    ),
                }
            )

        rows.sort(key=lambda row: row["advantage_kwh"], reverse=True)
        self._ranking = rows
        self._residual = self._compute_residual(rows)

        if not rows:
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        self._attr_native_value = rows[0]["device"]

    @callback
    def _compute_residual(self, rows: list[dict]) -> float | None:
        """Minus the sum of the ranked advantages — what the rest of the house did.

        Exact only when every profiled device reported; a device dropping out
        would otherwise be silently folded into the remainder and read as a
        fault of the unprofiled load.
        """
        if len(rows) != len(self._devices):
            return None
        return round(-sum(row["advantage_kwh"] for row in rows), 3)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "cycle": self._cycle,
            "ranking": self._ranking,
            "unprofiled_advantage_kwh": self._residual,
            "house_self_energy_kwh": _round_or_none(
                (s := self.hass.states.get(self._house_self)) and s.state, 3
            ),
            "house_consumption_kwh": _round_or_none(
                (s := self.hass.states.get(self._house_consumption)) and s.state, 3
            ),
        }


def _round_or_none(value, digits: int) -> float | None:
    parsed = _to_float(value)
    return None if parsed is None else round(parsed, digits)


def build(hass: HomeAssistant, device: dict, devices: list[dict]) -> list:
    """One ranking entity per configured period, over every profiled device."""
    periods = device.get("periods") or []
    return [
        SolarRankingSensor(
            hass,
            slug=f"{SYSTEM_PREFIX}_solar_ranking_{cycle}",
            cycle=cycle,
            devices=devices,
            house_self=f"sensor.{SYSTEM_PREFIX}_self_energy_{cycle}",
            house_consumption=f"sensor.{SYSTEM_PREFIX}_consumption_{cycle}",
        )
        for cycle in periods
    ]
