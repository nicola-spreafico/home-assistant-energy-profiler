"""Sensor platform: instantiate each device's family entities."""

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import families
from .lean import lean_available

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
    # No update_before_add: these entities are push-based (should_poll=False) and
    # seed themselves in async_added_to_hass.
    async_add_entities(entities)

    # Maintenance services inherited from the Lean core. Lean registers the same
    # services on its own platform only, so they cannot target entities added by
    # this integration — re-register them here under this domain. They resolve by
    # method name, hence they apply only to the LeanFamilyMeter (cycle meter)
    # entities; targeting any other EIM entity raises an error.
    platform = entity_platform.async_get_current_platform()
    # Idiomatic replacement for the old reset_* scripts. Deliberately a no-op on
    # entities that expose nothing to reset (means, live views, Lean meters).
    platform.async_register_entity_service("reset", {}, _async_reset)
    platform.async_register_entity_service(
        "calibrate",
        {vol.Required("value"): vol.Coerce(float)},
        "async_calibrate",
    )
    platform.async_register_entity_service(
        "import_history",
        {vol.Required("source_entity"): cv.entity_id},
        "async_import_history",
        supports_response=SupportsResponse.ONLY,
    )
    platform.async_register_entity_service(
        "thin_history",
        {},
        "async_thin_history",
        supports_response=SupportsResponse.ONLY,
    )
    platform.async_register_entity_service(
        "clear_history",
        {vol.Required("confirm_deletion"): cv.string},
        "async_clear_history",
        supports_response=SupportsResponse.ONLY,
    )
