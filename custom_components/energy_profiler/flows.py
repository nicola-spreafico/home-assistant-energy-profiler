"""House power flows: the base readings every per-device attribution starts from.

The user configures ``power_flows:`` with the sensors their inverter/meter
integration already exposes, in W. This module turns that block into the two
things the rest of the integration needs:

- :func:`resolve_flows` — the static shape: which channels exist, which entity
  ids to subscribe to. Computed once at setup.
- :func:`read_weights` — the live reading: the instantaneous W of each portion,
  as non-negative floats. Computed on every tick.

**What the numbers mean.** Each flow is a *contribution to the house load*, not
a production figure: ``solar`` is the part of the panels' output that reaches
the load, never the raw production (which also feeds the battery and the grid).
The three portions therefore sum to the load, and their ratios are the shares a
device's consumption is attributed with. See the Level 3 documentation for why
raw production silently skews the split.

**Why ``load`` is only ever used to derive ``solar``.** Grid import and battery
discharge are readings people have natively; solar-to-load almost never is. So
``load`` exists to compute that one missing portion as the remainder, and
declaring both ``load`` and ``solar`` is rejected by the schema as
over-specified rather than silently resolved one way or the other.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .const import (
    CONF_FLOW_BATTERY,
    CONF_FLOW_GRID,
    CONF_FLOW_LOAD,
    CONF_FLOW_SOLAR,
    CONF_POWER_FLOWS,
    FLOW_CHANNELS,
)

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def resolve_flows(device: dict[str, Any]) -> dict[str, Any] | None:
    """Return the resolved flow config for a device, or None if it has no split.

    The returned dict carries the entity ids plus ``channels``: the self-side
    channels that actually exist, in presentation order. An empty ``channels``
    list means the self share is real but unqualified (only ``load`` + ``grid``
    were given), so ``from_self`` exists with no solar/battery breakdown.
    """
    flows = device.get(CONF_POWER_FLOWS)
    if not flows:
        return None

    load = flows.get(CONF_FLOW_LOAD)
    solar = flows.get(CONF_FLOW_SOLAR)
    battery = flows.get(CONF_FLOW_BATTERY)

    # `load` present means solar is the derived remainder (the schema guarantees
    # solar was not also given). Without `load`, only what was declared exists.
    channels = [c for c in FLOW_CHANNELS if (solar if c == CONF_FLOW_SOLAR else battery)]
    if load and CONF_FLOW_SOLAR not in channels:
        # A derived solar channel only makes sense alongside a declared battery:
        # with `load` + `grid` alone the self share is real but unattributed.
        if battery:
            channels.insert(0, CONF_FLOW_SOLAR)

    return {
        CONF_FLOW_LOAD: load,
        CONF_FLOW_GRID: flows[CONF_FLOW_GRID],
        CONF_FLOW_SOLAR: solar,
        CONF_FLOW_BATTERY: battery,
        "channels": channels,
        "derives_solar": bool(load) and not solar,
    }


def source_entities(flows: dict[str, Any]) -> list[str]:
    """Entity ids whose changes must re-trigger a recalculation."""
    keys = (CONF_FLOW_LOAD, CONF_FLOW_GRID, CONF_FLOW_SOLAR, CONF_FLOW_BATTERY)
    return [eid for key in keys if (eid := flows.get(key))]


def read_weights(hass: HomeAssistant, flows: dict[str, Any]) -> dict[str, float] | None:
    """Read the live flows as non-negative W per portion, or None if unreadable.

    Clamping to zero is not cosmetic: a grid sensor that goes negative on export
    and a battery sensor that goes negative while charging are both common, and
    either would otherwise turn into a negative share (and, through the
    remainder, a portion above 100%).
    """
    grid = _to_float((s := hass.states.get(flows[CONF_FLOW_GRID])) and s.state)
    if grid is None:
        return None
    weights = {CONF_FLOW_GRID: max(0.0, grid)}

    battery_eid = flows.get(CONF_FLOW_BATTERY)
    if battery_eid:
        battery = _to_float((s := hass.states.get(battery_eid)) and s.state)
        if battery is None:
            return None
        weights[CONF_FLOW_BATTERY] = max(0.0, battery)

    if flows["derives_solar"]:
        load = _to_float((s := hass.states.get(flows[CONF_FLOW_LOAD])) and s.state)
        if load is None:
            return None
        # Whatever the load is not covered by grid or battery came from the panels.
        # Measurement noise can push this slightly negative around zero self-use.
        derived = load - weights[CONF_FLOW_GRID] - weights.get(CONF_FLOW_BATTERY, 0.0)
        if CONF_FLOW_SOLAR in flows["channels"]:
            weights[CONF_FLOW_SOLAR] = max(0.0, derived)
        elif derived > 0:
            # Unqualified self share: no channel to name it, but it still has to
            # weigh against the grid, so it rides as an unnamed self portion.
            weights["_self"] = derived
    else:
        solar_eid = flows.get(CONF_FLOW_SOLAR)
        if solar_eid:
            solar = _to_float((s := hass.states.get(solar_eid)) and s.state)
            if solar is None:
                return None
            weights[CONF_FLOW_SOLAR] = max(0.0, solar)

    return weights


def self_fraction(weights: dict[str, float]) -> float:
    """Share of the house load *not* covered by the grid, in 0..1.

    All flows at zero (or unavailable upstream) means there is nothing to
    attribute to self-production, so the tick is treated as fully grid-fed —
    the same worst-case default the percentage-based split used.
    """
    total = sum(weights.values())
    if total <= 0:
        return 0.0
    return (total - weights[CONF_FLOW_GRID]) / total


def solar_fraction_of_self(weights: dict[str, float]) -> float:
    """Share of the *self* portion that came from the panels, in 0..1.

    Only meaningful when both channels exist; the caller checks that first.
    """
    solar = weights.get(CONF_FLOW_SOLAR, 0.0)
    battery = weights.get(CONF_FLOW_BATTERY, 0.0)
    self_total = solar + battery
    if self_total <= 0:
        return 0.0
    return solar / self_total
