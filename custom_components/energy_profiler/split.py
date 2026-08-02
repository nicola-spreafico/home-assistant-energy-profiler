"""Attribution of a device's energy to the house's grid / solar / battery flows.

Nobody can know which electron reached the dishwasher. What this module does is
*attribution*: on each energy tick, a device is assumed to draw from the house
mix in the proportions the house itself is drawing at that instant, read from
``power_flows:`` (see flows.py).

**One splitter, one callback.** A single entity subscribes to the group's energy
source. On each tick it computes every portion from the same delta and the same
flow reading, then pushes each portion into its accumulator. Portions are
derived by *remainder* rather than computed independently, which makes the
invariants exact by construction rather than by luck:

    from_self + from_grid    == the delta        (always)
    from_solar + from_battery == from_self       (when both channels exist)

The splitter is itself the ``from_self`` accumulator — that portion always
exists whenever a split exists, so it is the natural owner of the subscription.

``SelfSufficiencyRatioSensor``'s successor, :class:`EnergyRatioSensor`, turns any
two of those accumulators into the live percentage view of the same split.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import logging

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_FLOW_BATTERY, CONF_FLOW_SOLAR, DEFAULT_PERCENTAGE_PRECISION
from .flows import read_weights, self_fraction, solar_fraction_of_self

_LOGGER = logging.getLogger(__name__)

# Energy deltas above this (kWh) are treated as meter resets / spikes and skipped.
DEFAULT_MAX_DELTA = 5.0

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class SplitPortionSensor(RestoreSensor):
    """Passive kWh accumulator, updated only by its splitter via ``add()``.

    Holds one portion of the split. It never tracks the energy source itself —
    the splitter owns the single atomic computation and pushes exact remainders
    here, so the portions can never drift apart.
    """

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "kWh"

    def __init__(self, hass: HomeAssistant, *, slug: str, icon: str, name: str | None = None) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._total = Decimal(0)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._total = Decimal(str(last.native_value))
            except (InvalidOperation, ValueError):
                self._total = Decimal(0)

    @property
    def native_value(self) -> Decimal:
        return self._total

    async def async_reset(self) -> None:
        """Zero the accumulated portion (reset entity service)."""
        self._total = Decimal(0)
        self.async_write_ha_state()

    @callback
    def add(self, delta: Decimal) -> None:
        """Add a portion computed by the splitter and publish the new total."""
        self._total += delta
        self.async_write_ha_state()


class EnergyFlowSplitter(SplitPortionSensor):
    """The ``from_self`` accumulator, which also drives every other portion.

    Subscribes once to the group's energy source. On each valid tick it reads the
    house flows, splits the delta, and updates itself plus each portion sensor
    atomically — same delta, same flow reading, one callback.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        energy_source: str,
        flows: dict,
        grid_portion: SplitPortionSensor,
        channel_portions: dict[str, SplitPortionSensor],
        icon: str,
        max_delta: float = DEFAULT_MAX_DELTA,
        name: str | None = None,
    ) -> None:
        super().__init__(hass, slug=slug, icon=icon, name=name)
        self._energy_source = energy_source
        self._flows = flows
        self._grid = grid_portion
        self._channels = channel_portions
        self._max_delta = max_delta
        self._last_energy: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = self.hass.states.get(self._energy_source)
        self._last_energy = _to_float(state.state if state else None)
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._energy_source], self._async_on_energy_change
            )
        )

    @callback
    def _async_on_energy_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        new_energy = _to_float(new_state.state if new_state else None)
        if new_energy is None:
            return

        previous = self._last_energy
        self._last_energy = new_energy
        if previous is None:
            return

        diff = new_energy - previous
        if not (0 < diff < self._max_delta):
            # Negative (meter reset), zero, or a spike: don't split it.
            return

        d_diff = Decimal(str(diff))

        # Flows unreadable -> worst case all-from-grid, so a broken sensor can
        # never inflate the self share (and with it the claimed savings).
        weights = read_weights(self.hass, self._flows)
        frac_self = self_fraction(weights) if weights is not None else 0.0

        self_portion = d_diff * Decimal(str(frac_self))
        grid_portion = d_diff - self_portion  # remainder: self + grid == diff, exactly

        self._total += self_portion
        self.async_write_ha_state()
        self._grid.add(grid_portion)

        if not self._channels:
            return

        solar = self._channels.get(CONF_FLOW_SOLAR)
        battery = self._channels.get(CONF_FLOW_BATTERY)
        if solar is not None and battery is not None:
            frac_solar = solar_fraction_of_self(weights) if weights is not None else 0.0
            solar_portion = self_portion * Decimal(str(frac_solar))
            solar.add(solar_portion)
            # remainder again: solar + battery == self, exactly
            battery.add(self_portion - solar_portion)
        elif solar is not None:
            # Single channel: the whole self share is that channel, by definition.
            solar.add(self_portion)
        elif battery is not None:
            battery.add(self_portion)


class EnergyRatioSensor(SensorEntity):
    """Live percentage view of the split: ``numerator / denominator * 100``.

    Used for self-sufficiency (``from_self / total``) and for each portion's
    share of the total. Reads two accumulators, so it is exact for whatever
    window they cover — a period meter's closed value gives the energy-weighted
    share of that period, not an average of instantaneous percentages.
    """

    _attr_should_poll = False
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Display only: the state keeps the 6 decimals the ratio is computed to.
    _attr_suggested_display_precision = DEFAULT_PERCENTAGE_PRECISION

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        numerator: str,
        denominator: str,
        icon: str = "mdi:solar-power-variant",
        name: str | None = None,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = name or slug
        self._attr_icon = icon
        self._numerator = numerator
        self._denominator = denominator
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._numerator, self._denominator], self._async_on_change
            )
        )

    @callback
    def _async_on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        total = _to_float((s := self.hass.states.get(self._denominator)) and s.state)
        portion = _to_float((s := self.hass.states.get(self._numerator)) and s.state)
        # No consumption in the cycle -> undefined (avoid div-by-zero and skewing LTS).
        if total is None or portion is None or total <= 0:
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        self._attr_native_value = round((portion / total) * 100, 6)
