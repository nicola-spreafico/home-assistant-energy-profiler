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

from .const import (
    CONF_ENERGY_PRICE,
    CONF_SELF_SUFFICIENCY_SOURCE,
    CONF_NAME_SUFFIX,
    CONF_LIVE_UPDATE_INTERVAL,
    CONF_PERIODS,
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
_INHERITABLE = (CONF_ENERGY_PRICE, CONF_SELF_SUFFICIENCY_SOURCE, CONF_LIVE_UPDATE_INTERVAL, CONF_PERIODS)


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

    Cost and solar-split are not families anymore: they are sub-blocks of each
    energy group's stack, driven by energy_price / self_sufficiency_source.
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
