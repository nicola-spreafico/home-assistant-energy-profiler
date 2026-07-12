"""Bridge to the Lean Utility Meter core.

Cumulative/cycle families (energy, cost, from_grid, ...) reuse Lean's cycle-writing
behavior by subclassing its sensor, so this integration writes one consolidated LTS
row per cycle without reimplementing the stats writer. The hard `dependencies` entry
in the manifest guarantees `lean_utility_meter` is loaded first, so this import is safe.
"""

from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.core import HomeAssistant

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

# Lean cycles this integration can create. Aligned with lean/period.py.
SUPPORTED_CYCLES = (
    "hourly", "daily", "weekly", "monthly", "bimonthly", "quarterly", "yearly",
)

DEFAULT_LIVE_UPDATE_INTERVAL = timedelta(minutes=5)


def lean_available() -> bool:
    """True if the Lean core is importable (runtime safety net for version drift)."""
    return LeanUtilityMeterSensor is not None


if LeanUtilityMeterSensor is not None:

    class LeanFamilyMeter(LeanUtilityMeterSensor):  # type: ignore[misc]
        """A cycle meter for one family, backed by the Lean core.

        Collapses Lean's verbose constructor into the handful of parameters a
        family builder actually varies, and *forces* entity_id, unit, device
        class and state class instead of relying on inheritance from the source
        (the old generator had to pin these via ``homeassistant.customize``
        because ``UtilityMeterSensor`` does not always adopt them reliably).
        """

        def __init__(
            self,
            hass: HomeAssistant,
            *,
            source: str,
            slug: str,
            cycle: str,
            unit: str,
            device_class: SensorDeviceClass | None,
            live_update_interval: timedelta = DEFAULT_LIVE_UPDATE_INTERVAL,
            net_consumption: bool = False,
            absolute_values: bool = False,
            always_available: bool = True,
            state_class: SensorStateClass = SensorStateClass.TOTAL,
            name: str | None = None,
        ) -> None:
            super().__init__(
                hass=hass,
                source_entity=source,
                name=name or slug,
                unique_id=slug,
                meter_type=cycle,
                meter_offset=timedelta(0),
                cron_pattern=None,
                delta_values=False,
                net_consumption=net_consumption,
                sensor_always_available=always_available,
                periodically_resetting=True,
                absolute_values=absolute_values,
                tariff=None,
                tariff_entity=None,
                parent_meter=slug,
                live_update_interval=live_update_interval,
            )
            # Pin the entity_id so it matches the historical snapshot ids exactly
            # (migration remaps nothing: same entity_id -> same LTS series).
            self.entity_id = f"sensor.{slug}"
            self._fixed_unit = unit
            self._fixed_device_class = device_class
            self._fixed_state_class = state_class

        # Force presentation instead of inheriting it from the source entity.
        @property
        def native_unit_of_measurement(self) -> str:
            return self._fixed_unit

        @property
        def device_class(self) -> SensorDeviceClass | None:
            return self._fixed_device_class

        @property
        def state_class(self) -> SensorStateClass:
            return self._fixed_state_class

else:  # pragma: no cover - only when the Lean core is missing
    LeanFamilyMeter = None  # type: ignore[assignment]


def build_cycle_meters(
    hass: HomeAssistant,
    device: dict,
    *,
    source: str,
    name_suffix: str,
    unit: str,
    device_class: SensorDeviceClass | None,
    net_consumption: bool = False,
    absolute_values: bool = False,
) -> list["LeanFamilyMeter"]:
    """Build one Lean meter per requested cycle for a device sub-metric.

    ``name_suffix`` is appended to the device prefix to form the slug/entity_id,
    e.g. prefix ``foo_em`` + suffix ``energy`` + cycle ``daily`` ->
    ``sensor.foo_em_energy_daily``.
    """
    if LeanFamilyMeter is None:
        return []

    prefix = device["prefix"]
    cycles = device.get("cycles") or ["daily", "monthly", "yearly"]
    live_update_interval = device.get("live_update_interval") or DEFAULT_LIVE_UPDATE_INTERVAL

    meters: list[LeanFamilyMeter] = []
    for cycle in cycles:
        if cycle not in SUPPORTED_CYCLES:
            _LOGGER.warning("Skipping unsupported cycle %r for %s", cycle, prefix)
            continue
        meters.append(
            LeanFamilyMeter(
                hass,
                source=source,
                slug=f"{prefix}_{name_suffix}_{cycle}",
                cycle=cycle,
                unit=unit,
                device_class=device_class,
                live_update_interval=live_update_interval,
                net_consumption=net_consumption,
                absolute_values=absolute_values,
            )
        )
    return meters
