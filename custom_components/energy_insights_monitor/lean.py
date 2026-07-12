"""Bridge to the Lean Utility Meter core.

Cumulative/cycle families (energy, cost, from_grid, ...) reuse Lean's cycle-writing
behavior by subclassing its sensor, so this integration writes one consolidated LTS
row per cycle without reimplementing the stats writer. The hard `dependencies` entry
in the manifest guarantees `lean_utility_meter` is loaded first, so this import is safe.
"""

import logging

_LOGGER = logging.getLogger(__name__)

# Inherit the Lean cycle-meter behavior. Kept behind a try/except with an explicit
# error so a breaking change in Lean's internal API fails loudly rather than silently.
try:
    from custom_components.lean_utility_meter.entity import LeanUtilityMeterSensor
except Exception as err:  # pragma: no cover - guarded by manifest dependency
    LeanUtilityMeterSensor = None
    _LOGGER.error(
        "Energy Insights Monitor requires the 'lean_utility_meter' integration; "
        "could not import its core (%s)", err,
    )


def lean_available() -> bool:
    """True if the Lean core is importable (runtime safety net for version drift)."""
    return LeanUtilityMeterSensor is not None
