"""Per-device resolution and family selection.

`build_device_config` merges a device's YAML against the shared defaults and
decides which entity *families* it gets — the same conditional logic that lived
in the old generator's `main.py` (render_basics, render_self_sufficiency, ...).

Signals vs consumers: `running:` alone only creates the running gatekeeper
(built by the binary_sensor platform based on its presence, outside the family
selection). The cycles *family* is the analytics consumer and requires both
`running:` and `cycle_tracking:`.
"""

import logging
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    SYSTEM_DEVICE_ID,
    SYSTEM_DEVICE_NAME,
    CONF_ENERGY_PRICE,
    CONF_POWER_FLOWS,
    CONF_NAME_SUFFIX,
    CONF_LIVE_UPDATE_INTERVAL,
    CONF_PERIODS,
    CONF_INSTANT_PERIODS,
    CONF_COST_PRECISION,
    CONF_NAME,
    CONF_RUNNING,
    CONF_CYCLE_TRACKING,
    CONF_STANDBY,
    FAMILY_POWER,
    FAMILY_ENERGY,
    FAMILY_RUNNING,
    FAMILY_CYCLES,
    FAMILY_STANDBY,
)

_LOGGER = logging.getLogger(__name__)

# Keys that a device may override from `defaults`.
_INHERITABLE = (
    CONF_ENERGY_PRICE,
    CONF_POWER_FLOWS,
    CONF_LIVE_UPDATE_INTERVAL,
    CONF_PERIODS,
    CONF_INSTANT_PERIODS,
    CONF_COST_PRECISION,
)


def entity_label(slug: str, prefix: str) -> str:
    """The human-readable name of an entity, with its device prefix stripped.

    Entities carry `has_entity_name`, so Home Assistant renders them as
    "<device> <name>". The device already says which appliance this is, and
    repeating it would give "Dishwasher dishwasher_em_cycle_completed_cost".
    What is left is the measurement alone: "Cycle completed cost".

    Sentence case, per Home Assistant's own naming style — only the first word
    and proper nouns are capitalised.
    """
    label = slug.removeprefix(f"{prefix}_").replace("_", " ").strip()
    if not label:
        # A slug that *is* the prefix: nothing left to name it by.
        return slug.replace("_", " ")
    return label[0].upper() + label[1:]


def system_device_info() -> DeviceInfo:
    """The one house-level device: shared readings, not tied to any appliance."""
    return DeviceInfo(
        identifiers={(DOMAIN, SYSTEM_DEVICE_ID)},
        name=SYSTEM_DEVICE_NAME,
        manufacturer="Energy Profiler",
        model="House flows",
        entry_type=None,
    )


def device_info_for(resolved: dict[str, Any]) -> DeviceInfo:
    """The device page for one profiled appliance.

    ``via_device`` hangs every appliance off the system device, so the UI shows
    the house readings as the parent of the devices derived from them.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, resolved["prefix"])},
        name=resolved[CONF_NAME],
        manufacturer="Energy Profiler",
        model="Device profile",
        via_device=(DOMAIN, SYSTEM_DEVICE_ID),
    )


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
    """Decide which entity families to build, from what the config declares.

    Cost and the grid/solar/battery split are not families anymore: they are
    sub-blocks of each energy group's stack, driven by energy_price / power_flows.
    """
    families = [FAMILY_POWER, FAMILY_ENERGY]  # always on

    # running-energy group: same stack as the total, gated on the running signal
    if resolved.get(CONF_RUNNING):
        families.append(FAMILY_RUNNING)

    # run-cycle analytics: an explicit consumer of the running signal
    if resolved.get(CONF_CYCLE_TRACKING) is not None:
        if resolved.get(CONF_RUNNING):
            families.append(FAMILY_CYCLES)
        else:
            _LOGGER.warning(
                "Device %s enables cycle_tracking but has no 'running' block; the "
                "analytics need the running signal — skipping the cycles family",
                resolved["prefix"],
            )

    # standby (+cost) energy tracking
    if resolved.get(CONF_STANDBY):
        families.append(FAMILY_STANDBY)

    return families
