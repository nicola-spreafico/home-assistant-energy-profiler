"""Per-device resolution and family selection.

`build_device_config` merges a device's YAML against the shared defaults and
decides which entity *families* it gets — the same conditional logic that lived
in the old generator's `main.py` (render_basics, render_self_sufficiency, ...).
"""

from typing import Any

from .const import (
    CONF_ENERGY_PRICE,
    CONF_SELF_SUFFICIENCY_SOURCE,
    CONF_NAME_SUFFIX,
    CONF_LIVE_UPDATE_INTERVAL,
    CONF_CYCLES,
    CONF_NAME,
    CONF_RUN,
    CONF_STANDBY,
    FAMILY_POWER,
    FAMILY_ENERGY,
    FAMILY_COST,
    FAMILY_SELF_SUFFICIENCY,
    FAMILY_CYCLES,
    FAMILY_STANDBY,
)

# Keys that a device may override from `defaults`.
_INHERITABLE = (CONF_ENERGY_PRICE, CONF_SELF_SUFFICIENCY_SOURCE, CONF_LIVE_UPDATE_INTERVAL, CONF_CYCLES)


def build_device_config(device: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Return a fully-resolved device spec: merged config + enabled families + prefix."""
    resolved = dict(device)

    for key in _INHERITABLE:
        if key not in resolved and key in defaults:
            resolved[key] = defaults[key]

    suffix = defaults.get(CONF_NAME_SUFFIX, "")
    resolved["prefix"] = f"{device[CONF_NAME]}{suffix}"

    resolved["families"] = _enabled_families(resolved)
    return resolved


def _enabled_families(resolved: dict[str, Any]) -> list[str]:
    """Decide which entity families to build, from what the config declares."""
    families = [FAMILY_POWER, FAMILY_ENERGY, FAMILY_COST]  # always on

    # from_self / from_grid / savings / grid_cost + self-sufficiency %
    if resolved.get(CONF_SELF_SUFFICIENCY_SOURCE):
        families.append(FAMILY_SELF_SUFFICIENCY)

    # cycle tracking (running counters/durations) only if a `run` block is given
    if resolved.get(CONF_RUN):
        families.append(FAMILY_CYCLES)

    # standby (+cost) energy tracking
    if resolved.get(CONF_STANDBY):
        families.append(FAMILY_STANDBY)

    return families
