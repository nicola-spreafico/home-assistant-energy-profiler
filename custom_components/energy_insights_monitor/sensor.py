"""Sensor platform: instantiate each device's family entities."""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import families
from .lean import lean_available

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities: AddEntitiesCallback, discovery_info=None):
    """Build the entity list for every resolved device and add it."""
    if not discovery_info:
        return

    if not lean_available():
        _LOGGER.error(
            "Lean Utility Meter core is not importable; no Energy Insights Monitor "
            "entities will be created. Is the 'lean_utility_meter' integration installed?"
        )
        return

    entities = []
    for device in discovery_info.get("devices", []):
        entities.extend(families.build_entities(hass, device))

    _LOGGER.debug("Energy Insights Monitor: adding %d entities", len(entities))
    # update_before_add=True so meters seed from their source on startup, matching
    # how the Lean platform adds its own entities.
    async_add_entities(entities, True)
