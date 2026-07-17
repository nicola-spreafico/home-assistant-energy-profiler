"""Family builders — the modules that replace the generator's 24 YAML fragments.

Each module owns one feature area and returns the entities for a device given its
resolved config. `build_entities` dispatches based on device["families"] (decided
in device.py), which mirrors the old main.py render_* orchestration.
"""

from ..const import (
    CONF_RUNNING,
    FAMILY_POWER, FAMILY_ENERGY, FAMILY_COST, FAMILY_SELF_SUFFICIENCY, FAMILY_CYCLES, FAMILY_STANDBY,
)
from . import power, energy, cost, self_sufficiency, cycles, standby

_BUILDERS = {
    FAMILY_POWER: power.build,
    FAMILY_ENERGY: energy.build,
    FAMILY_COST: cost.build,
    FAMILY_SELF_SUFFICIENCY: self_sufficiency.build,
    FAMILY_CYCLES: cycles.build,
    FAMILY_STANDBY: standby.build,
}


def build_entities(hass, device):
    """Return all sensor-platform entities for a device across its enabled families."""
    entities = []
    for family in device.get("families", []):
        builder = _BUILDERS.get(family)
        if builder:
            entities.extend(builder(hass, device))
    return entities


def build_binary_sensors(hass, device):
    """Return all binary_sensor-platform entities (the gatekeepers) for a device.

    ``_running`` is a *signal*: it is created whenever the device declares a
    ``running:`` block, whether or not the cycles analytics consume it.
    ``_standby`` follows the ``standby`` option's flavor.
    """
    entities = []
    if device.get(CONF_RUNNING):
        entities.extend(cycles.build_binary_sensors(hass, device))
    if FAMILY_STANDBY in device.get("families", []):
        entities.extend(standby.build_binary_sensors(hass, device))
    return entities
