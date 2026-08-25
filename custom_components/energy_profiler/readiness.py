"""Cycle-readiness timestamp estimates for battery charge and solar forecast."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import CONF_SOLCAST_TODAY, CONF_SOLCAST_TOMORROW

SOLCAST_ATTRIBUTE = "detailedForecast"
SOLCAST_DATETIME_KEY = "period_start"
SOLCAST_POWER_KEY = "pv_estimate"

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


class BatteryCycleReadyAtSensor(SensorEntity):
    """When the current battery charge rate will cover one average cycle."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:battery-clock"

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        battery_energy_source: str,
        battery_charge_power_source: str,
        cycle_energy_source: str,
        cycle_count_source: str,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = slug
        self._battery_energy_source = battery_energy_source
        self._battery_charge_power_source = battery_charge_power_source
        self._cycle_energy_source = cycle_energy_source
        self._cycle_count_source = cycle_count_source
        self._attr_native_value = None
        self._attributes: dict = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [
                    self._battery_energy_source,
                    self._battery_charge_power_source,
                    self._cycle_energy_source,
                    self._cycle_count_source,
                ],
                self._on_source_change,
            )
        )
        self._recalculate()

    @callback
    def _on_source_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        battery = self.hass.states.get(self._battery_energy_source)
        charge = self.hass.states.get(self._battery_charge_power_source)
        cycle = self.hass.states.get(self._cycle_energy_source)
        count = self.hass.states.get(self._cycle_count_source)

        battery_kwh = _to_float(battery.state if battery else None)
        charge_w = _to_float(charge.state if charge else None)
        cycle_kwh = _to_float(cycle.state if cycle else None)
        cycle_count = _to_float(count.state if count else None)
        self._attributes = {
            "battery_energy_source": self._battery_energy_source,
            "battery_charge_power_source": self._battery_charge_power_source,
            "cycle_energy_source": self._cycle_energy_source,
            "estimate": "linear_at_current_charge_power",
        }

        if (
            battery_kwh is None
            or battery_kwh < 0
            or cycle_kwh is None
            or cycle_kwh <= 0
            or cycle_count is None
            or cycle_count < 1
        ):
            self._set_unavailable("invalid_or_missing_cycle_or_battery")
            return

        deficit_kwh = max(cycle_kwh - battery_kwh, 0.0)
        self._attributes.update(
            {
                "battery_available_energy_kwh": round(battery_kwh, 3),
                "average_cycle_energy_kwh": round(cycle_kwh, 3),
                "energy_deficit_kwh": round(deficit_kwh, 3),
                "battery_charge_power_w": round(charge_w, 1)
                if charge_w is not None
                else None,
                "valid_cycles": int(cycle_count),
            }
        )

        now = dt_util.now()
        if deficit_kwh == 0:
            self._attr_available = True
            self._attr_native_value = now
            self._attributes["status"] = "already_available"
            self._attributes["hours_until_ready"] = 0.0
            return

        if charge_w is None or charge_w <= 0:
            self._set_unavailable("battery_not_charging")
            return

        hours = deficit_kwh / (charge_w / 1000.0)
        self._attr_available = True
        self._attr_native_value = now + timedelta(hours=hours)
        self._attributes["status"] = "charging"
        self._attributes["hours_until_ready"] = round(hours, 2)

    @callback
    def _set_unavailable(self, status: str) -> None:
        self._attr_available = False
        self._attr_native_value = None
        self._attributes["status"] = status

    @property
    def extra_state_attributes(self) -> dict:
        return self._attributes


@dataclass(frozen=True)
class ForecastPeriod:
    start: datetime
    end: datetime
    power_kw: float


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = dt_util.parse_datetime(value)
    else:
        return None
    if result is None or result.tzinfo is None:
        return None
    return dt_util.as_utc(result)


def forecast_periods(
    hass: HomeAssistant,
    *,
    entities: list[str],
) -> list[ForecastPeriod]:
    """Normalize Solcast's detailed forecast points into contiguous periods."""

    points: dict[datetime, float] = {}
    for entity_id in entities:
        state = hass.states.get(entity_id)
        raw = state.attributes.get(SOLCAST_ATTRIBUTE) if state is not None else None
        if not isinstance(raw, (list, tuple)):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            when = _parse_datetime(item.get(SOLCAST_DATETIME_KEY))
            power_kw = _to_float(item.get(SOLCAST_POWER_KEY))
            if when is None or power_kw is None or power_kw < 0:
                continue
            points[when] = power_kw

    ordered = sorted(points.items())
    if len(ordered) < 2:
        return []

    deltas = [
        (ordered[index + 1][0] - ordered[index][0]).total_seconds()
        for index in range(len(ordered) - 1)
        if ordered[index + 1][0] > ordered[index][0]
    ]
    if not deltas:
        return []
    deltas.sort()
    typical_seconds = deltas[len(deltas) // 2]

    periods = []
    for index, (start, power_kw) in enumerate(ordered):
        next_start = (
            ordered[index + 1][0]
            if index + 1 < len(ordered)
            else start + timedelta(seconds=typical_seconds)
        )
        end = min(next_start, start + timedelta(seconds=typical_seconds))
        if end > start:
            periods.append(ForecastPeriod(start, end, power_kw))
    return periods


def first_continuous_window(
    periods: list[ForecastPeriod],
    *,
    now: datetime,
    duration: timedelta,
    required_power_kw: float,
) -> datetime | None:
    """Earliest forecast instant meeting the power threshold for the full duration."""

    for index, period in enumerate(periods):
        if period.end <= now or period.power_kw < required_power_kw:
            continue
        candidate = max(now, period.start)
        target = candidate + duration
        covered_until = candidate

        for following in periods[index:]:
            if following.end <= covered_until:
                continue
            if following.start > covered_until or following.power_kw < required_power_kw:
                break
            covered_until = following.end
            if covered_until >= target:
                return candidate
    return None


class SolarCycleReadyAtSensor(SensorEntity):
    """Earliest forecast window able to power one average appliance cycle."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:solar-power-variant"

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        solcast_forecast: dict,
        house_load_source: str,
        device_power_source: str,
        cycle_energy_source: str,
        cycle_duration_source: str,
        cycle_count_source: str,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = slug
        self._solcast_entities = [
            solcast_forecast[CONF_SOLCAST_TODAY],
            solcast_forecast[CONF_SOLCAST_TOMORROW],
        ]
        self._house_load_source = house_load_source
        self._device_power_source = device_power_source
        self._cycle_energy_source = cycle_energy_source
        self._cycle_duration_source = cycle_duration_source
        self._cycle_count_source = cycle_count_source
        self._attr_native_value = None
        self._attributes: dict = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [
                    *self._solcast_entities,
                    self._house_load_source,
                    self._device_power_source,
                    self._cycle_energy_source,
                    self._cycle_duration_source,
                    self._cycle_count_source,
                ],
                self._on_source_change,
            )
        )
        self._recalculate()

    @callback
    def _on_source_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        load = self.hass.states.get(self._house_load_source)
        device_power = self.hass.states.get(self._device_power_source)
        cycle_energy = self.hass.states.get(self._cycle_energy_source)
        cycle_duration = self.hass.states.get(self._cycle_duration_source)
        cycle_count = self.hass.states.get(self._cycle_count_source)

        load_w = _to_float(load.state if load else None)
        device_w = _to_float(device_power.state if device_power else None)
        cycle_kwh = _to_float(cycle_energy.state if cycle_energy else None)
        duration_s = _to_float(cycle_duration.state if cycle_duration else None)
        count = _to_float(cycle_count.state if cycle_count else None)
        self._attributes = {
            "solcast_forecast_entities": self._solcast_entities,
            "house_load_source": self._house_load_source,
            "device_power_source": self._device_power_source,
            "cycle_energy_source": self._cycle_energy_source,
            "cycle_duration_source": self._cycle_duration_source,
            "estimate": "continuous_average_cycle_power",
            "house_load_assumption": "current_load_minus_current_device_power",
        }

        if (
            load_w is None
            or load_w < 0
            or device_w is None
            or device_w < 0
            or cycle_kwh is None
            or cycle_kwh <= 0
            or duration_s is None
            or duration_s <= 0
            or count is None
            or count < 1
        ):
            self._set_unavailable("invalid_or_missing_cycle_or_load")
            return

        current_device_w = device_w
        baseline_w = max(load_w - current_device_w, 0.0)
        cycle_average_kw = cycle_kwh / (duration_s / 3600.0)
        required_kw = baseline_w / 1000.0 + cycle_average_kw
        periods = forecast_periods(
            self.hass,
            entities=self._solcast_entities,
        )
        now = dt_util.as_utc(dt_util.now())
        future_periods = [period for period in periods if period.end > now]
        ready_at = first_continuous_window(
            future_periods,
            now=now,
            duration=timedelta(seconds=duration_s),
            required_power_kw=required_kw,
        )
        self._attributes.update(
            {
                "house_load_power_w": round(load_w, 1),
                "device_current_power_w": round(current_device_w, 1),
                "house_baseline_power_w": round(baseline_w, 1),
                "average_cycle_energy_kwh": round(cycle_kwh, 3),
                "average_cycle_duration_s": round(duration_s),
                "average_cycle_power_kw": round(cycle_average_kw, 3),
                "required_solar_power_kw": round(required_kw, 3),
                "valid_cycles": int(count),
                "forecast_periods": len(future_periods),
                "forecast_horizon_end": (
                    future_periods[-1].end.isoformat() if future_periods else None
                ),
            }
        )

        if not future_periods:
            self._set_unavailable("forecast_unavailable")
            return
        if ready_at is None:
            self._set_unavailable("no_suitable_window_in_forecast")
            return

        self._attr_available = True
        self._attr_native_value = ready_at
        self._attributes["status"] = "window_found"

    @callback
    def _set_unavailable(self, status: str) -> None:
        self._attr_available = False
        self._attr_native_value = None
        self._attributes["status"] = status

    @property
    def extra_state_attributes(self) -> dict:
        return self._attributes
