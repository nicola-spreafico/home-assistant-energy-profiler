"""Family: cycles.

Replaces the generator's ``003_cycles`` fragments: a run-detection state machine
(binary_sensor ``_running`` from a power threshold or a custom template), cycle
start/stop snapshots, per-cycle live energy/cost, a completed-cycle counter with
min/max duration+energy limits, and an optional completion notification.

IMPLEMENTED so far: the run-detection ``_running`` binary sensor (the gatekeeper
every other cycle/standby feature keys off).

DEFERRED (out of the first migration wave, per the plan): the rest of the family —
cycle start/stop snapshots, per-cycle live energy/cost, completed-cycle counters
with min/max duration+energy limits, means and the completion notification. Those
are counters/durations/event automations rather than cumulative energy, so they do
not benefit from the Lean consolidation and are migrated separately.
"""

from ..const import (
    CONF_POWER,
    CONF_RUN,
    CONF_TRIGGER,
    CONF_ON_ABOVE,
    CONF_OFF_BELOW,
    CONF_ON_DELAY,
    CONF_OFF_DELAY,
    CONF_AVAILABLE,
    CONF_STATE,
)


def running_entity_id(prefix: str) -> str:
    """The ``_running`` binary sensor id — the gatekeeper for cycle/standby logic."""
    return f"binary_sensor.{prefix}_running"


def build(hass, device):
    """Sensor-platform entities for cycles. Deferred (counters/durations/means)."""
    return []


def build_binary_sensors(hass, device):
    """Return the ``_running`` binary sensor if the device declares a ``run`` block."""
    run = device.get(CONF_RUN)
    if not run:
        return []

    # Imported lazily: the binary_sensor platform module imports this package, and
    # importing it at module load would create a cycle through families/__init__.
    from ..binary_sensor import PowerRunningBinarySensor, TemplateRunningBinarySensor

    prefix = device["prefix"]
    slug = f"{prefix}_running"

    if run[CONF_TRIGGER] == "power":
        return [
            PowerRunningBinarySensor(
                hass,
                slug=slug,
                power_source=device[CONF_POWER],
                on_above=run[CONF_ON_ABOVE],
                off_below=run[CONF_OFF_BELOW],
                on_delay=run[CONF_ON_DELAY],
                off_delay=run[CONF_OFF_DELAY],
            )
        ]

    # trigger: template
    return [
        TemplateRunningBinarySensor(
            hass,
            slug=slug,
            state_template=run[CONF_STATE],
            availability_template=run.get(CONF_AVAILABLE),
        )
    ]
