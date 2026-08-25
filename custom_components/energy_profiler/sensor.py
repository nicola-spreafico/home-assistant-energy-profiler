"""Sensor platform: instantiate each device's family entities.

Family builders return a mix of two things: Entity objects owned by this
integration, and Lean meter *specs* (plain dicts, see lean.py). Both are added
here, on **this** platform — the meters are built with Lean's public
``meter_from_spec`` rather than dispatched to Lean's own platform by discovery.

That choice is what makes the device pages complete. Home Assistant attaches an
entity to a device only when its platform is backed by a config entry, and
Lean's platform (discovery-based, YAML-first) has none; meters dispatched there
would stay device-less, which is most of what you would want to chart. Owning
them here costs one thing — Lean's maintenance services are registered on Lean's
platform, not ours — so we re-register them, by the same method names, and
``thin_history`` & co. keep targeting these meters exactly as before. Lean's
repairs are unaffected: they are scheduled by the entity itself.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.helpers import entity_registry as er

from . import families, system
from .const import CONF_INCLUDE_IN_RANKING, DOMAIN, SYSTEM_PREFIX
from .device import (
    device_info_for,
    entity_label,
    prosumption_device_info,
    self_consumption_device_info,
    self_sufficiency_device_info,
    system_device_info,
)
from .lean import LEAN_DOMAIN, lean_available

_LOGGER = logging.getLogger(__name__)


@callback
def _reclaim_meter_registry_entries(hass: HomeAssistant, specs: list[dict]) -> None:
    """Drop registry entries left behind when the meters lived on Lean's platform.

    The entity registry keys on (domain, platform, unique_id). Meters that used
    to be dispatched to ``lean_utility_meter`` are registered under *its*
    platform; recreating them here would be seen as brand-new entities, and the
    stale rows would still hold the entity ids — so every meter would come back
    as ``..._2`` and its long-term statistics, which are keyed by entity id,
    would be orphaned.

    Removing the old row lets the new entity claim the same entity id and keep
    its whole history. Deliberately narrow: only rows that are under Lean's
    platform, carry a unique id this integration generates, *and* already occupy
    exactly the entity id we are about to pin. A user's own Lean meter can match
    none of those three at once.
    """
    registry = er.async_get(hass)
    for spec in specs:
        unique_id = spec.get("unique_id")
        pinned = spec.get("entity_id")
        if not unique_id or not pinned:
            continue
        existing = registry.async_get_entity_id(SENSOR_DOMAIN, LEAN_DOMAIN, unique_id)
        if existing is None or existing != pinned:
            continue
        _LOGGER.info(
            "Migrating %s from the %s platform to %s (same entity id, history kept)",
            existing, LEAN_DOMAIN, DOMAIN,
        )
        registry.async_remove(existing)


@callback
def _drop_excluded_ranking_registry_entries(
    hass: HomeAssistant, devices: list[dict]
) -> None:
    """Remove stale comparison entities for devices excluded from ranking.

    Long-term statistics are intentionally left in place. Re-enabling the
    device recreates the same entity ids and reconnects their history.
    """
    registry = er.async_get(hass)
    for device in devices:
        if device.get(CONF_INCLUDE_IN_RANKING, True):
            continue
        prefix = device["prefix"]
        for cycle in device.get("periods") or []:
            for metric in ("index", "advantage"):
                stem = f"{prefix}_energy_from_self_{metric}_{cycle}"
                for unique_id in (stem, f"{stem}_live"):
                    existing = registry.async_get_entity_id(
                        SENSOR_DOMAIN, DOMAIN, unique_id
                    )
                    if existing is None:
                        continue
                    _LOGGER.info(
                        "Removing %s because %s has include_in_ranking: false",
                        existing,
                        prefix,
                    )
                    registry.async_remove(existing)


async def _async_reset(entity, call) -> None:
    """Reset an accumulator/peak entity; no-op when the entity is not resettable."""
    reset = getattr(entity, "async_reset", None)
    if reset is None:
        _LOGGER.debug("reset: %s has nothing to reset; ignoring", entity.entity_id)
        return
    await reset()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Build the entity list for every resolved device and add it."""
    if not lean_available(hass):
        _LOGGER.error(
            "Lean Utility Meter is not set up; no Energy Profiler "
            "entities will be created. Is the 'lean_utility_meter' integration installed?"
        )
        return

    from custom_components.lean_utility_meter.sensor import (
        meter_from_spec,
        register_entity_services,
    )

    store = hass.data[DOMAIN]
    devices = store.get("devices", [])

    entities: list = []
    specs: list[dict] = []

    def _collect(items, info, prefix: str) -> None:
        """Sort a builder's mixed output, tagging both kinds with their device."""
        for item in items:
            if isinstance(item, dict):
                # A Lean meter spec: tag it with the device and its label before
                # it is built, so the meter lands on the same page as its own
                # accumulator and reads the same way.
                item["device_info"] = info
                item["has_entity_name"] = True
                item["name"] = entity_label(item["unique_id"], prefix)
                specs.append(item)
            else:
                item._attr_device_info = info
                item._attr_has_entity_name = True
                item._attr_name = entity_label(item.entity_id.split(".", 1)[1], prefix)
                entities.append(item)

    house_groups = system.build_house_energy(
        hass, store.get("defaults", {}), devices
    )

    # The integration root keeps configuration and the shared counters/flows.
    _collect(
        system.build_configuration(hass, store.get("defaults", {}), devices)
        + house_groups["system"],
        system_device_info(),
        SYSTEM_PREFIX,
    )

    # Each global score family gets its own child device, including its Lean
    # period meters and hidden live helpers.
    for key, info in (
        ("self_sufficiency", self_sufficiency_device_info()),
        ("self_consumption", self_consumption_device_info()),
        ("prosumption", prosumption_device_info()),
    ):
        _collect(house_groups[key], info, SYSTEM_PREFIX)

    for device in devices:
        _collect(families.build_entities(hass, device), device_info_for(device), device["prefix"])

    # Must run before the meters are added, so the entity ids are free to reclaim.
    _drop_excluded_ranking_registry_entries(hass, devices)
    _reclaim_meter_registry_entries(hass, specs)
    for spec in specs:
        meter = meter_from_spec(hass, spec)
        if spec.get("hidden"):
            # Only bites on first registration; a meter already in the registry
            # keeps whatever visibility it has (the user's choice wins there).
            meter._attr_entity_registry_visible_default = False
        entities.append(meter)
    meter_count = len(specs)

    _LOGGER.debug(
        "Energy Profiler: adding %d entities (%d of them Lean meters)",
        len(entities), meter_count,
    )
    # No update_before_add for our own push-based entities, but the Lean meters
    # do need their first read, and a mixed list must take the stricter option.
    async_add_entities(entities, True)

    platform = entity_platform.async_get_current_platform()
    # Idiomatic replacement for the old reset_* scripts. Deliberately a no-op on
    # entities that expose nothing to reset (means, live views).
    platform.async_register_entity_service("reset", {}, _async_reset)
    # Lean's own maintenance services (calibrate, thin_history, import_history,
    # clear_history), re-registered here because the meters live on this platform.
    register_entity_services()
