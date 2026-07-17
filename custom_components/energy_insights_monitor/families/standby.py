"""Family: standby.

Replaces the generator's ``004_standby`` fragments: the energy (and its cost)
drawn while the device is in *standby* — idle/vampire consumption.

Everything is gated on a first-class ``binary_sensor.<prefix>_standby``
gatekeeper, whose flavor is chosen by the ``standby`` option:

- ``standby: true`` — the default: standby is simply "``_running`` is off"
  (requires the ``running`` block; skipped with a warning otherwise);
- ``standby: {trigger: power, on_below: ...}`` — standby when the power draw
  stays inside the vampire range (inverted thresholds vs ``running``);
- ``standby: {trigger: template, ...}`` — a custom condition.

While the gatekeeper is on, the group accumulates the standby energy through
the shared energy stack (see energy_stack.py) — same block as the total and
running groups: energy, solar/grid split, costs, %, period meters — plus the
``_standby_duration`` live counter.
"""

import logging

from ..const import (
    CONF_AVAILABLE,
    CONF_OFF_ABOVE,
    CONF_OFF_DELAY,
    CONF_ON_BELOW,
    CONF_ON_DELAY,
    CONF_POWER,
    CONF_RUNNING,
    CONF_STANDBY,
    CONF_STATE,
    CONF_TRIGGER,
)
from .cycles import running_entity_id
from .energy import lifetime_entity_id
from . import energy_stack

_LOGGER = logging.getLogger(__name__)


def standby_entity_id(prefix: str) -> str:
    """The ``_standby`` binary sensor id — the gatekeeper for the standby family."""
    return f"binary_sensor.{prefix}_standby"


def _default_mode_misconfigured(device) -> bool:
    """True when `standby: true` was requested without the `running` block it needs."""
    return device.get(CONF_STANDBY) is True and not device.get(CONF_RUNNING)


def has_gatekeeper(device) -> bool:
    """True when the device will actually get a ``_standby`` binary sensor."""
    return bool(device.get(CONF_STANDBY)) and not _default_mode_misconfigured(device)


def build_binary_sensors(hass, device):
    """Return the ``_standby`` gatekeeper in the configured flavor."""
    standby = device.get(CONF_STANDBY)
    if not standby:
        return []

    prefix = device["prefix"]
    if _default_mode_misconfigured(device):
        _LOGGER.warning(
            "Device %s enables standby (default flavor) but has no 'running' block; the "
            "default gates on running=off, so it needs running detection — skipping "
            "standby family. Use a custom standby trigger to go without 'running'.",
            prefix,
        )
        return []

    from ..binary_sensor import (
        PowerStandbyBinarySensor,
        StandbyFromRunningBinarySensor,
        TemplateStandbyBinarySensor,
    )

    slug = f"{prefix}_standby"
    if standby is True:
        return [
            StandbyFromRunningBinarySensor(
                hass, slug=slug, running_entity=running_entity_id(prefix)
            )
        ]
    if standby[CONF_TRIGGER] == "power":
        return [
            PowerStandbyBinarySensor(
                hass,
                slug=slug,
                power_source=device[CONF_POWER],
                on_below=standby[CONF_ON_BELOW],
                off_above=standby.get(CONF_OFF_ABOVE),
                on_delay=standby[CONF_ON_DELAY],
                off_delay=standby[CONF_OFF_DELAY],
            )
        ]
    return [
        TemplateStandbyBinarySensor(
            hass,
            slug=slug,
            state_template=standby[CONF_STATE],
            availability_template=standby.get(CONF_AVAILABLE),
        )
    ]


def build(hass, device):
    """Return the standby energy stack plus the live standby duration."""
    prefix = device["prefix"]

    if _default_mode_misconfigured(device):
        return []  # already warned in build_binary_sensors

    from ..cycles_tracker import StandbyDurationSensor

    entities = energy_stack.build_stack(
        hass, device,
        name_base="standby_energy",
        # Gate the decoupled lifetime's deltas on the standby gatekeeper.
        source=lifetime_entity_id(prefix),
        gate_entity=standby_entity_id(prefix),
    )
    entities.append(
        StandbyDurationSensor(
            hass, slug=f"{prefix}_standby_duration", standby_entity=standby_entity_id(prefix),
        )
    )
    return entities
