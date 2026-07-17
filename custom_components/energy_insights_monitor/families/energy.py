"""Group: total energy — the ungated view of the device's consumption.

The full energy stack (see energy_stack.py) sourced from the hardware energy
sensor with no gate: the base ``_energy_lifetime`` is the decoupled all-time
total every other group and family reads from (it accumulates only positive
increments, so a plug swap or a sensor-id change never resets the number nor
injects a phantom delta downstream). Also the only group with the instantaneous
cost projections. Entity ids preserved from the old generator
(``sensor.<prefix>_energy_*``) so migrations keep the same LTS series.
"""

from ..const import CONF_ENERGY
from . import energy_stack


def lifetime_entity_id(prefix: str) -> str:
    """The energy lifetime entity id — the shared source for all downstream families."""
    return f"sensor.{prefix}_energy_lifetime"


def build(hass, device):
    """Return the total-energy stack for a resolved device."""
    return energy_stack.build_stack(
        hass, device,
        name_base="energy",
        source=device[CONF_ENERGY],
        include_instant=True,
    )
