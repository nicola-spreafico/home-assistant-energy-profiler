"""Family builders — the modules that replace the generator's 24 YAML fragments.

Each module owns one feature area and returns the entities for a device given its
resolved config. `build_entities` dispatches based on device["families"] (decided
in device.py), which mirrors the old main.py render_* orchestration.
"""

from ..const import (
    FAMILY_ENERGY, FAMILY_COST, FAMILY_SELF_SUFFICIENCY, FAMILY_CYCLES, FAMILY_STANDBY,
)
from . import energy, cost, self_sufficiency, cycles, standby

_BUILDERS = {
    FAMILY_ENERGY: energy.build,
    FAMILY_COST: cost.build,
    FAMILY_SELF_SUFFICIENCY: self_sufficiency.build,
    FAMILY_CYCLES: cycles.build,
    FAMILY_STANDBY: standby.build,
}


def build_entities(hass, device):
    """Return all entities for a device across its enabled families."""
    entities = []
    for family in device.get("families", []):
        builder = _BUILDERS.get(family)
        if builder:
            entities.extend(builder(hass, device))
    return entities
