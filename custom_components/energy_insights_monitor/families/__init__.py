"""Family builders — the modules that replace the generator's 24 YAML fragments.

Each module owns one feature area and returns the entities for a device given its
resolved config. `build_entities` dispatches based on device["families"] (decided
in device.py), which mirrors the old main.py render_* orchestration.
"""

from ..const import (
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
    """Return all binary_sensor-platform entities for a device.

    Two families contribute gatekeepers: cycles (``_running``, when the device
    declares a ``run`` block) and standby (``_standby``, in the flavor chosen by
    the ``standby`` option).
    """
    families_enabled = device.get("families", [])
    entities = []
    if FAMILY_CYCLES in families_enabled:
        entities.extend(cycles.build_binary_sensors(hass, device))
    if FAMILY_STANDBY in families_enabled:
        entities.extend(standby.build_binary_sensors(hass, device))
    return entities
