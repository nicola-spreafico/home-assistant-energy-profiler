"""Sensor platform: instantiate each device's family entities."""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import families

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities: AddEntitiesCallback, discovery_info=None):
    """Build the entity list for every resolved device and add it."""
    if not discovery_info:
        return

    entities = []
    for device in discovery_info.get("devices", []):
        entities.extend(families.build_entities(hass, device))

    _LOGGER.debug("Energy Monitor: adding %d entities", len(entities))
    async_add_entities(entities)
