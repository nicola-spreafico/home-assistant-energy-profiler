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
    """Sensor-platform entities for cycles: count + duration (Lean-backed) and the
    last-completed snapshots. Means and the completion notification are deferred."""
    if not device.get(CONF_RUN):
        return []

    from homeassistant.components.sensor import SensorDeviceClass

    from ..cycles_tracker import (
        CompletedValueSensor,
        CycleEnergyAccumulatorSensor,
        CycleTrackerSensor,
        DurationAccumulatorSensor,
        MeanSensor,
    )
    from ..lean import build_cycle_meters
    from .energy import lifetime_entity_id

    prefix = device["prefix"]
    count_lifetime = f"{prefix}_cycles_count_lifetime"
    duration_lifetime = f"{prefix}_cycles_duration_lifetime"
    energy_total = f"{prefix}_cycles_energy_lifetime"

    completed_energy = CompletedValueSensor(
        hass, slug=f"{prefix}_cycle_completed_energy",
        unit="kWh", device_class=SensorDeviceClass.ENERGY, icon="mdi:lightning-bolt",
    )
    completed_duration = CompletedValueSensor(
        hass, slug=f"{prefix}_cycle_completed_duration",
        unit="s", device_class=SensorDeviceClass.DURATION, icon="mdi:timer-outline",
    )
    duration_acc = DurationAccumulatorSensor(
        hass, slug=duration_lifetime, icon="mdi:timer-sand",
    )
    energy_acc = CycleEnergyAccumulatorSensor(
        hass, slug=energy_total, icon="mdi:lightning-bolt-outline",
    )
    tracker = CycleTrackerSensor(
        hass,
        slug=count_lifetime,
        running_entity=running_entity_id(prefix),
        energy_entity=lifetime_entity_id(prefix),
        duration_accumulator=duration_acc,
        energy_accumulator=energy_acc,
        completed_energy=completed_energy,
        completed_duration=completed_duration,
    )

    # Per-completed-cycle means (total-so-far / cycles-so-far).
    energy_mean = MeanSensor(
        hass, slug=f"{prefix}_cycles_energy_mean",
        total_entity=f"sensor.{energy_total}", count_entity=f"sensor.{count_lifetime}",
        unit="kWh", device_class=SensorDeviceClass.ENERGY, icon="mdi:lightning-bolt",
    )
    duration_mean = MeanSensor(
        hass, slug=f"{prefix}_cycles_duration_mean",
        total_entity=f"sensor.{duration_lifetime}", count_entity=f"sensor.{count_lifetime}",
        unit="s", device_class=SensorDeviceClass.DURATION, icon="mdi:timer-outline",
    )

    entities = [
        tracker, duration_acc, energy_acc, completed_energy, completed_duration,
        energy_mean, duration_mean,
    ]
    # Cumulative -> Lean cycle meters give cycles-per-period and run-time-per-period.
    entities += build_cycle_meters(
        hass, device, source=f"sensor.{count_lifetime}",
        name_suffix="cycles_count", unit=None, device_class=None,
    )
    entities += build_cycle_meters(
        hass, device, source=f"sensor.{duration_lifetime}",
        name_suffix="cycles_duration", unit="s", device_class=SensorDeviceClass.DURATION,
    )
    return entities


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
