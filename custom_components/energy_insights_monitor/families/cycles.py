"""Family: cycles.

Replaces the generator's ``003_cycles`` fragments: a run-detection state machine
(binary_sensor ``_running`` from a power threshold or a custom template), cycle
start/stop snapshots, per-cycle live energy/cost, a completed-cycle counter with
min/max duration+energy limits, and an optional completion notification.

DEFERRED (out of the first migration wave, per the plan): this family is not
meter-like — it is counters, durations and event automations rather than
cumulative energy — so it does not benefit from the Lean consolidation and is
migrated separately (or left on the old packages) after the energy/cost/
self-sufficiency wave lands. The run-detection state machine implemented here is
also a prerequisite for the standby family.
"""


def build(hass, device):
    """Return the cycle-tracking entities for a resolved device. Deferred."""
    return []
