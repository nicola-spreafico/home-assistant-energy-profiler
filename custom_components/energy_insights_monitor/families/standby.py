"""Family: standby.

Replaces the generator's ``004_standby`` fragments: the energy (and its cost)
drawn while the device is *not* running — i.e. consumption accumulated since the
last cycle stopped.

DEFERRED (out of the first migration wave): standby depends on the cycles family,
which is itself deferred. It reads ``binary_sensor.<prefix>_running`` and the
``final_energy_total`` attribute of ``sensor.<prefix>_cycle_stop_snapshot`` to
decide when the device is idle, so it cannot be built before cycle tracking
exists. Once cycles lands, the standby energy lifetime becomes a normal cost-style
integrator feeding per-cycle Lean meters.
"""


def build(hass, device):
    """Return the standby entities for a resolved device. Deferred (needs cycles)."""
    return []
