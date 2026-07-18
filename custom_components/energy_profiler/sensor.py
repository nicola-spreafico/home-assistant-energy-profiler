"""Sensor platform: instantiate each device's family entities.

Family builders return a mix of two things: Entity objects owned by this
integration, and Lean meter *specs* (plain dicts, see lean.py). The entities are
added here; the specs are forwarded via discovery to the ``lean_utility_meter``
sensor platform, which owns the resulting meters — so Lean's native maintenance
services (``lean_utility_meter.thin_history``, ...) target them directly.
"""

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import families
from .const import DOMAIN
from .lean import LEAN_DOMAIN, lean_available

_LOGGER = logging.getLogger(__name__)


async def _async_reset(entity, call) -> None:
    """Reset an accumulator/peak entity; no-op when the entity is not resettable."""
    reset = getattr(entity, "async_reset", None)
    if reset is None:
        _LOGGER.debug("reset: %s has nothing to reset; ignoring", entity.entity_id)
        return
    await reset()


async def async_setup_platform(hass, config, async_add_entities: AddEntitiesCallback, discovery_info=None):
    """Build the entity list for every resolved device and add it."""
    if not discovery_info:
        return

    if not lean_available(hass):
        _LOGGER.error(
            "Lean Utility Meter is not set up; no Energy Profiler "
            "entities will be created. Is the 'lean_utility_meter' integration installed?"
        )
        return

    items = []
    for device in discovery_info.get("devices", []):
        items.extend(families.build_entities(hass, device))

    meter_specs = [item for item in items if isinstance(item, dict)]
    entities = [item for item in items if not isinstance(item, dict)]

    _LOGGER.debug(
        "Energy Profiler: adding %d entities, dispatching %d Lean meters",
        len(entities), len(meter_specs),
    )
    # No update_before_add: these entities are push-based (should_poll=False) and
    # seed themselves in async_added_to_hass.
    async_add_entities(entities)

    # The cycle meters are created BY the lean_utility_meter platform, so they are
    # native Lean entities (its services and repairs apply with no glue here).
    if meter_specs:
        hass.async_create_task(
            async_load_platform(
                hass,
                Platform.SENSOR,
                LEAN_DOMAIN,
                {"meters": meter_specs},
                hass.data[DOMAIN].get("hass_config", {}),
            )
        )

    platform = entity_platform.async_get_current_platform()
    # Idiomatic replacement for the old reset_* scripts. Deliberately a no-op on
    # entities that expose nothing to reset (means, live views).
    platform.async_register_entity_service("reset", {}, _async_reset)
