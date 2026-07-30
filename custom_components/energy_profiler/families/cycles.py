"""Family: cycles — appliance run-cycle tracking and analytics.

Replaces the whole ``003_cycles`` folder:
- ``_running`` gatekeeper (binary sensor, ``build_binary_sensors``);
- start/stop snapshots, validation against min/max limits;
- per-metric completed values, live (in-progress) values and means, for energy and
  (when the families exist) cost, from_self, from_grid, savings, grid_cost;
- count and duration, exposed per-period via Lean meters;
- ``cycle_completed`` / ``cycle_discarded`` events for user automations.
- ``cycle_completed_start/stop``: the frozen boundaries of the last valid cycle,
  which the start/stop snapshots cannot stand in for (they track the cycle in
  progress, so mid-run they are one cycle apart).
"""

from ..const import (
    CONF_POWER,
    CONF_RUNNING,
    CONF_CYCLE_TRACKING,
    CONF_TRIGGER,
    CONF_ON_ABOVE,
    CONF_OFF_BELOW,
    CONF_ON_DELAY,
    CONF_OFF_DELAY,
    CONF_AVAILABLE,
    CONF_STATE,
    CONF_LIMITS,
    CONF_ENERGY_PRICE,
    CONF_SELF_SUFFICIENCY_SOURCE,
    CONF_SOLAR_SHARE_SOURCE,
    CONF_BATTERY_SHARE_SOURCE,
    CONF_COST_PRECISION,
    DEFAULT_COST_PRECISION,
    DEFAULT_PERCENTAGE_PRECISION,
)


def running_entity_id(prefix: str) -> str:
    """The ``_running`` binary sensor id — the gatekeeper for cycle/standby logic."""
    return f"binary_sensor.{prefix}_running"


def build(hass, device):
    """All sensor-platform cycle entities (snapshots, completed, live, means, meters)."""
    run = device.get(CONF_RUNNING)
    tracking = device.get(CONF_CYCLE_TRACKING)
    if not run or tracking is None:
        return []

    from homeassistant.components.sensor import SensorDeviceClass

    from ..cycles_tracker import (
        CompletedTimestampSensor,
        CompletedValueSensor,
        CycleLiveDurationSensor,
        CycleLiveSensor,
        CycleSnapshotSensor,
        CycleSumAccumulatorSensor,
        CycleTrackerSensor,
        CycleValidationSensor,
        DurationAccumulatorSensor,
        HumanDurationSensor,
        MeanSensor,
        ScaledRatioSensor,
    )
    from ..lean import build_period_meters
    from ..split import SelfSufficiencyRatioSensor

    prefix = device["prefix"]
    running = running_entity_id(prefix)
    count_lifetime = f"{prefix}_cycles_count_lifetime"
    duration_lifetime = f"{prefix}_cycles_duration_lifetime"
    ENERGY = SensorDeviceClass.ENERGY
    MONEY = SensorDeviceClass.MONETARY
    DURATION = SensorDeviceClass.DURATION

    price = device.get(CONF_ENERGY_PRICE)
    has_self = device.get(CONF_SELF_SUFFICIENCY_SOURCE)
    cost_precision = device.get(CONF_COST_PRECISION, DEFAULT_COST_PRECISION)

    # Snapshots + validation status.
    start_snap = CycleSnapshotSensor(hass, slug=f"{prefix}_cycle_start_snapshot", icon="mdi:timer-marker-outline")
    stop_snap = CycleSnapshotSensor(hass, slug=f"{prefix}_cycle_stop_snapshot", icon="mdi:timer-marker-outline")
    # The snapshots above move with the cycle in progress; these two freeze the
    # boundaries of the last valid one, so the pair is always self-consistent.
    completed_start = CompletedTimestampSensor(hass, slug=f"{prefix}_cycle_completed_start", icon="mdi:play-circle-outline")
    completed_stop = CompletedTimestampSensor(hass, slug=f"{prefix}_cycle_completed_stop", icon="mdi:stop-circle-outline")
    validation = CycleValidationSensor(hass, slug=f"{prefix}_cycle_validation_status")
    entities = [start_snap, stop_snap, completed_start, completed_stop, validation]

    # Metrics: (name, source lifetime, completed, mean, accumulator, live) — energy
    # always, the rest gated on the cost / self-sufficiency families existing.
    metrics: list = []

    def metric(name, source_slug, completed_slug, mean_slug, acc_slug, live_slug, unit, dc, icon):
        # The € metrics need an explicit precision (HA has no default for the
        # monetary device class); kWh and durations get theirs from their own.
        prec = cost_precision if dc is MONEY else None
        completed = CompletedValueSensor(hass, slug=completed_slug, unit=unit, device_class=dc, icon=icon, display_precision=prec)
        acc = CycleSumAccumulatorSensor(hass, slug=acc_slug, unit=unit, device_class=dc, icon=icon, display_precision=prec)
        mean = MeanSensor(
            hass, slug=mean_slug, total_entity=acc.entity_id,
            count_entity=f"sensor.{count_lifetime}", unit=unit, device_class=dc, icon=icon,
            display_precision=prec,
        )
        live = CycleLiveSensor(
            hass, slug=live_slug, source_entity=f"sensor.{source_slug}",
            snapshot_entity=start_snap.entity_id, initial_attr=f"initial_{name}",
            running_entity=running, unit=unit, device_class=dc, icon=icon,
            display_precision=prec,
        )
        metrics.append((name, f"sensor.{source_slug}", completed, acc))
        entities.extend([completed, acc, mean, live])

    metric("energy", f"{prefix}_energy_lifetime", f"{prefix}_cycle_completed_energy",
           f"{prefix}_cycles_energy_mean", f"{prefix}_cycles_energy_lifetime",
           f"{prefix}_cycle_live_energy", "kWh", ENERGY, "mdi:lightning-bolt")
    if price:
        metric("cost", f"{prefix}_energy_cost_lifetime", f"{prefix}_cycle_completed_cost",
               f"{prefix}_cycles_cost_mean", f"{prefix}_cycles_cost_lifetime",
               f"{prefix}_cycle_live_cost", "€", MONEY, "mdi:cash")
    if has_self:
        metric("from_self", f"{prefix}_energy_from_self_lifetime", f"{prefix}_cycle_completed_energy_from_self",
               f"{prefix}_cycles_energy_from_self_mean", f"{prefix}_cycles_energy_from_self_lifetime",
               f"{prefix}_cycle_live_energy_from_self", "kWh", ENERGY, "mdi:solar-panel")
        metric("from_grid", f"{prefix}_energy_from_grid_lifetime", f"{prefix}_cycle_completed_energy_from_grid",
               f"{prefix}_cycles_energy_from_grid_mean", f"{prefix}_cycles_energy_from_grid_lifetime",
               f"{prefix}_cycle_live_energy_from_grid", "kWh", ENERGY, "mdi:transmission-tower")
    # Second-level split of self (solar vs battery): e.g. how much sun vs how
    # much battery a washing-machine run actually used.
    if has_self and (device.get(CONF_SOLAR_SHARE_SOURCE) or device.get(CONF_BATTERY_SHARE_SOURCE)):
        metric("from_solar", f"{prefix}_energy_from_solar_lifetime", f"{prefix}_cycle_completed_energy_from_solar",
               f"{prefix}_cycles_energy_from_solar_mean", f"{prefix}_cycles_energy_from_solar_lifetime",
               f"{prefix}_cycle_live_energy_from_solar", "kWh", ENERGY, "mdi:weather-sunny")
        metric("from_battery", f"{prefix}_energy_from_battery_lifetime", f"{prefix}_cycle_completed_energy_from_battery",
               f"{prefix}_cycles_energy_from_battery_mean", f"{prefix}_cycles_energy_from_battery_lifetime",
               f"{prefix}_cycle_live_energy_from_battery", "kWh", ENERGY, "mdi:home-battery")
    if price and has_self:
        metric("savings", f"{prefix}_energy_from_grid_savings_lifetime", f"{prefix}_cycle_completed_energy_from_grid_savings",
               f"{prefix}_cycles_energy_from_grid_savings_mean", f"{prefix}_cycles_energy_from_grid_savings_lifetime",
               f"{prefix}_cycle_live_savings_from_grid", "€", MONEY, "mdi:piggy-bank")
        metric("grid_cost", f"{prefix}_energy_from_grid_cost_lifetime", f"{prefix}_cycle_completed_energy_from_grid_cost",
               f"{prefix}_cycles_energy_from_grid_cost_mean", f"{prefix}_cycles_energy_from_grid_cost_lifetime",
               f"{prefix}_cycle_live_cost_from_grid", "€", MONEY, "mdi:cash-minus")

    # Duration (special: measured from the boundary timestamps, not a source delta).
    duration_acc = DurationAccumulatorSensor(hass, slug=duration_lifetime, icon="mdi:timer-sand")
    completed_duration = CompletedValueSensor(hass, slug=f"{prefix}_cycle_completed_duration", unit="s", device_class=DURATION, icon="mdi:timer-outline")
    duration_mean = MeanSensor(hass, slug=f"{prefix}_cycles_duration_mean", total_entity=duration_acc.entity_id, count_entity=f"sensor.{count_lifetime}", unit="s", device_class=DURATION, icon="mdi:timer-outline")
    live_duration = CycleLiveDurationSensor(hass, slug=f"{prefix}_cycle_live_duration", start_snapshot=start_snap.entity_id, running_entity=running)
    entities += [duration_acc, completed_duration, duration_mean, live_duration]

    # Self-sufficiency % (completed + mean over cycles + live), when applicable.
    completed_ss = None
    if has_self:
        completed_ss = CompletedValueSensor(hass, slug=f"{prefix}_cycle_completed_self_sufficiency", unit="%", device_class=None, icon="mdi:solar-power-variant", display_precision=DEFAULT_PERCENTAGE_PRECISION)
        entities += [
            completed_ss,
            SelfSufficiencyRatioSensor(
                hass, slug=f"{prefix}_cycles_self_sufficiency_percentage_mean",
                numerator=f"sensor.{prefix}_cycles_energy_from_self_lifetime",
                denominator=f"sensor.{prefix}_cycles_energy_lifetime",
            ),
            SelfSufficiencyRatioSensor(
                hass, slug=f"{prefix}_cycle_live_self_sufficiency",
                numerator=f"sensor.{prefix}_cycle_live_energy_from_self",
                denominator=f"sensor.{prefix}_cycle_live_energy",
            ),
        ]

    # Cost-over-time (€/h): completed value + mean over cycles (only when priced).
    completed_cot = None
    if price:
        completed_cot = CompletedValueSensor(hass, slug=f"{prefix}_cycle_completed_costovertime", unit="€/h", device_class=None, icon="mdi:cash-clock")
        entities += [
            completed_cot,
            ScaledRatioSensor(
                hass, slug=f"{prefix}_cycles_costovertime_mean",
                numerator=f"sensor.{prefix}_cycles_cost_lifetime",
                denominator=f"sensor.{duration_lifetime}", scale=3600, unit="€/h", icon="mdi:cash-clock",
            ),
        ]
    # Human-readable total run time.
    entities.append(
        HumanDurationSensor(hass, slug=f"{prefix}_cycles_duration_summary_human", seconds_source=f"sensor.{duration_lifetime}")
    )

    tracker = CycleTrackerSensor(
        hass,
        slug=count_lifetime,
        device_prefix=prefix,
        running_entity=running,
        metrics=metrics,
        duration_accumulator=duration_acc,
        completed_duration=completed_duration,
        start_snapshot=start_snap,
        stop_snapshot=stop_snap,
        completed_start=completed_start,
        completed_stop=completed_stop,
        validation=validation,
        limits=tracking.get(CONF_LIMITS) or {},
        on_delay=run.get(CONF_ON_DELAY),
        off_delay=run.get(CONF_OFF_DELAY),
        completed_self_sufficiency=completed_ss,
        completed_costovertime=completed_cot,
    )
    entities.append(tracker)

    # Cumulative count / duration -> Lean per-period meters.
    entities += build_period_meters(hass, device, source=f"sensor.{count_lifetime}", name_suffix="cycles_count", unit=None, device_class=None)
    entities += build_period_meters(hass, device, source=f"sensor.{duration_lifetime}", name_suffix="cycles_duration", unit="s", device_class=DURATION)
    return entities


def build_binary_sensors(hass, device):
    """Return the ``_running`` binary sensor if the device declares a ``running:`` block.

    The signal is independent from the analytics: it is built whenever the
    detection is configured, even with no ``cycle_tracking``.
    """
    run = device.get(CONF_RUNNING)
    if not run:
        return []

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

    return [
        TemplateRunningBinarySensor(
            hass,
            slug=slug,
            state_template=run[CONF_STATE],
            availability_template=run.get(CONF_AVAILABLE),
        )
    ]
