"""Family: energy.

Replaces the generator's ``001_basics/basics_002_[energy]`` fragment.

The old fragment built, per cycle, a transient ``utility_meter`` plus a template
snapshot sensor captured at 23:59:55 (thousands of LTS rows). Here a single Lean
meter per cycle collapses that into one consolidated LTS row per cycle, sourced
directly from the hardware energy sensor (a ``total_increasing`` kWh meter) — the
same source the old transient meters used.

Entity ids are preserved (``sensor.<prefix>_energy_<cycle>``) so the historical
migration keeps the same LTS series.
"""

from homeassistant.components.sensor import SensorDeviceClass

from ..const import CONF_ENERGY
from ..lean import build_cycle_meters


def build(hass, device):
    """Return the energy cycle meters for a resolved device."""
    return build_cycle_meters(
        hass,
        device,
        source=device[CONF_ENERGY],
        name_suffix="energy",
        unit="kWh",
        device_class=SensorDeviceClass.ENERGY,
    )
