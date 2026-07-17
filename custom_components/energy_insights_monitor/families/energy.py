"""Family: energy.

Replaces the generator's ``001_basics/basics_002_[energy]`` fragment.

The old fragment built, per cycle, a transient ``utility_meter`` plus a template
snapshot sensor captured at 23:59:55 (thousands of LTS rows), plus a no-cycle
``_energy_lifetime`` for the all-time total. Here:

- a single :class:`EnergyLifetimeSensor` accumulates the all-time total, decoupled
  from the raw hardware sensor (survives plug swaps / id changes);
- one Lean meter per cycle collapses each period into a single consolidated LTS row,
  **sourced from the lifetime** (not the hw sensor) so the whole chain inherits that
  decoupling.

Entity ids are preserved (``sensor.<prefix>_energy_<cycle>`` and
``sensor.<prefix>_energy_lifetime``) so the historical migration keeps the same
LTS series and the same all-time entity.
"""

from homeassistant.components.sensor import SensorDeviceClass

from ..const import CONF_ENERGY
from ..lean import build_period_meters
from ..lifetime import EnergyLifetimeSensor


def lifetime_entity_id(prefix: str) -> str:
    """The energy lifetime entity id — the shared source for all downstream families."""
    return f"sensor.{prefix}_energy_lifetime"


def build(hass, device):
    """Return the energy lifetime accumulator plus one Lean meter per cycle."""
    prefix = device["prefix"]
    lifetime_slug = f"{prefix}_energy_lifetime"

    entities = [
        EnergyLifetimeSensor(hass, slug=lifetime_slug, energy_source=device[CONF_ENERGY]),
    ]
    entities += build_period_meters(
        hass,
        device,
        source=f"sensor.{lifetime_slug}",
        name_suffix="energy",
        unit="kWh",
        device_class=SensorDeviceClass.ENERGY,
    )
    return entities
