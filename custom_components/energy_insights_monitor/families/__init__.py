"""Family builders — the modules that replace the generator's 24 YAML fragments.

Each module owns one feature area and returns the entities for a device given its
resolved config. `build_entities` dispatches based on device["families"] (decided
in device.py), which mirrors the old main.py render_* orchestration.
"""

from ..const import (
    CONF_RUNNING,
    FAMILY_POWER, FAMILY_ENERGY, FAMILY_RUNNING, FAMILY_CYCLES, FAMILY_STANDBY,
)
from . import power, energy, running, cycles, standby

_BUILDERS = {
    FAMILY_POWER: power.build,
    FAMILY_ENERGY: energy.build,
    FAMILY_RUNNING: running.build,
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
    entities.extend(_build_status(hass, device))
    return entities


def _build_status(hass, device):
    """The ``_status`` dashboard label, when at least one gatekeeper exists.

    Presentation-only: derived from the running/standby binary sensors, never
    consumed by internal logic.
    """
    from ..status import DeviceStatusSensor

    has_running = bool(device.get(CONF_RUNNING))
    has_standby = standby.has_gatekeeper(device)
    if not has_running and not has_standby:
        return []

    prefix = device["prefix"]
    return [
        DeviceStatusSensor(
            hass,
            slug=f"{prefix}_status",
            running_entity=cycles.running_entity_id(prefix) if has_running else None,
            standby_entity=standby.standby_entity_id(prefix) if has_standby else None,
        )
    ]


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
