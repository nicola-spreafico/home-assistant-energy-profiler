"""Group: running energy — consumption gated on the ``_running`` signal.

The same stack as the total group (see energy_stack.py), accumulated only while
``binary_sensor.<prefix>_running`` is on. This is what lets you split running vs
standby consumption *without* tracking cycles: unlike the cycles family's
``cycles_energy_lifetime`` (which only counts validated runs), this counts every
running moment, limits or no limits. Sourced from the decoupled total lifetime.
"""

from .cycles import running_entity_id
from .energy import lifetime_entity_id
from . import energy_stack


def build(hass, device):
    """Return the running-energy stack for a resolved device."""
    prefix = device["prefix"]
    return energy_stack.build_stack(
        hass, device,
        name_base="running_energy",
        source=lifetime_entity_id(prefix),
        gate_entity=running_entity_id(prefix),
    )
