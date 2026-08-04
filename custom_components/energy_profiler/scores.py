"""Derived scores: the sensors that compare one accumulator against another.

Everything here divides or subtracts quantities that some accumulator already
holds. Nothing here reads a power sensor, and that is the point: a score meant
to be *persisted for a period* has to be built from the two energies of that
period. The instantaneous view is a dashboard reading and nothing more — its
time-average over a day is not the day's figure, and the discrepancy is
``cov(power, self-share) / mean(power)``, i.e. precisely the "did you run things
while the sun was up" signal these scores exist to capture.

Four kinds of comparison live here:

- :class:`SelfEnergySensor` — ``consumption − import``, the self-consumed energy,
  accumulated from signed deltas so meter resets cannot leak into it.
- :class:`MinDenominatorRatioSensor` — ``numerator / min(a, b)``, the prosumption
  score: measure against whichever side was actually scarce.
- :class:`BaselineIndexSensor` / :class:`BaselineAdvantageSensor` — a device
  against the house baseline for the same period, as a multiplier and in kWh.
- :class:`EnergyBalanceSensor` — the cross-check between the two independent
  readings of the self-consumed energy.
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
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_state_change_event

from .const import DEFAULT_INDEX_PRECISION
from .lean import build_period_meters
from .split import DEFAULT_MAX_DELTA, EnergyRatioSensor

_LOGGER = logging.getLogger(__name__)

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_float(value) -> float | None:
    if value in _INVALID:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class DeltaCombinationSensor(RestoreSensor):
    """Accumulates a signed combination of house counters' *deltas*, in kWh.

    Never subtracts raw totals. House counters are lifetime meters that were
    started on whatever day each device was installed, so the difference of two
    of them is dominated by an arbitrary offset — on a real system the two
    readings of the same self-consumed energy sat 1574 kWh apart purely because
    the production meter had been running years longer than the consumption one.
    Accumulating deltas anchors every term at zero on first observation, which
    makes the result mean what it claims from the first tick.

    The same treatment handles what the offsets would otherwise hide: a counter
    that is reset or swapped drops one delta instead of dumping its whole
    history into the total.

    The running value can dip — grid import ticks a moment before the
    consumption meter catches up — so period meters over it are built with
    ``net_consumption`` and track the signed change. Over any window that closes
    properly the result is exact.
    """

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "kWh"

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        terms: dict[str, int],
        icon: str,
        max_delta: float = DEFAULT_MAX_DELTA,
        visible: bool = True,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = slug
        self._attr_icon = icon
        self._attr_entity_registry_visible_default = visible
        # {entity_id: +1 | -1} — the sign each counter's delta enters with.
        self._terms = terms
        self._max_delta = max_delta
        self._total = Decimal(0)
        self._last: dict[str, float | None] = {eid: None for eid in terms}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._total = Decimal(str(last.native_value))
            except (InvalidOperation, ValueError):
                self._total = Decimal(0)
        # Re-anchor on the current readings: whatever the house did while Home
        # Assistant was down is not attributable to any period we observed, and
        # counting it now would dump it all into the period we restart in.
        for entity_id in self._last:
            state = self.hass.states.get(entity_id)
            self._last[entity_id] = _to_float(state.state if state else None)
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, list(self._last), self._async_on_change
            )
        )

    @property
    def native_value(self) -> Decimal:
        return self._total

    async def async_reset(self) -> None:
        """Zero the accumulated total (reset entity service)."""
        self._total = Decimal(0)
        self.async_write_ha_state()

    @callback
    def _async_on_change(self, event: Event) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data.get("new_state")
        reading = _to_float(new_state.state if new_state else None)
        if reading is None:
            return

        previous = self._last[entity_id]
        self._last[entity_id] = reading
        if previous is None:
            return

        diff = reading - previous
        # Negative (meter reset / replacement) or implausibly large (spike): the
        # counter moved for a reason that is not energy flowing, so skip it
        # rather than let it land in the total.
        if not (0 < diff < self._max_delta):
            return

        self._total += Decimal(str(diff)) * self._terms[entity_id]
        self.async_write_ha_state()


class SelfEnergySensor(DeltaCombinationSensor):
    """``consumption − import``: the self-consumed energy of the house."""

    def __init__(self, hass: HomeAssistant, *, slug: str, consumption: str,
                 grid_import: str, icon: str = "mdi:solar-power-variant") -> None:
        super().__init__(
            hass, slug=slug, icon=icon,
            terms={consumption: 1, grid_import: -1},
        )


class MinDenominatorRatioSensor(EnergyRatioSensor):
    """``numerator / min(a, b) * 100`` — the prosumption score.

    Self-sufficiency divides by consumption, self-consumption divides by
    production, and each is capped by the *other* side: with production below
    consumption no behaviour can push self-sufficiency past
    ``production/consumption``, and above it the same is true of
    self-consumption in reverse. Dividing by the smaller of the two therefore
    always measures against the binding constraint — which is what makes the
    result a score of *coupling in time* rather than of plant sizing.

    Equivalent to ``max(self-sufficiency, self-consumption)``, since the larger
    ratio is by definition the one with the smaller denominator.
    """

    def __init__(self, hass: HomeAssistant, *, slug: str, numerator: str,
                 denominator: str, alternate: str, **kwargs) -> None:
        super().__init__(hass, slug=slug, numerator=numerator,
                         denominator=denominator, **kwargs)
        self._alternate = alternate

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._alternate], self._async_on_change
            )
        )

    @callback
    def _recalculate(self) -> None:
        portion = _to_float((s := self.hass.states.get(self._numerator)) and s.state)
        first = _to_float((s := self.hass.states.get(self._denominator)) and s.state)
        second = _to_float((s := self.hass.states.get(self._alternate)) and s.state)
        if portion is None or first is None or second is None:
            self._attr_available = False
            self._attr_native_value = None
            return
        total = min(first, second)
        if total <= 0:
            # Nothing produced or nothing consumed: there was no coupling to
            # score, which is not the same as having coupled nothing.
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        # Clamped both ways. 100 is the ceiling by construction — the score is a
        # fraction of the achievable maximum — and measurement noise can put the
        # numerator a hair above the scarce side. Zero is the floor for the same
        # reason it is on every other ratio here: overnight the self-consumed
        # energy is a difference of two counters that do not tick together, and
        # it wanders either side of the zero it should be sitting on.
        self._attr_native_value = round(min(max(portion / total * 100, 0.0), 100.0), 6)


class _BaselineSensor(SensorEntity):
    """Base for the two views of "this device versus the house, same period"."""

    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        slug: str,
        sources: list[str],
        icon: str,
        visible: bool = True,
    ) -> None:
        self.hass = hass
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = slug
        self._attr_name = slug
        self._attr_icon = icon
        self._sources = sources
        self._attr_native_value = None
        # Hidden helpers feed a period meter and nothing else: the meter owns
        # the public name and the long-term series, so a second one here would
        # be the same numbers recorded the wrong way round.
        self._attr_entity_registry_visible_default = visible
        if not visible:
            self._attr_state_class = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._recalculate()
        self.async_on_remove(
            async_track_state_change_event(self.hass, self._sources, self._on_change)
        )

    @callback
    def _on_change(self, event: Event) -> None:
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _unavailable(self) -> None:
        self._attr_available = False
        self._attr_native_value = None

    @callback
    def _recalculate(self) -> None:
        raise NotImplementedError


class BaselineIndexSensor(_BaselineSensor):
    """How many times better than the house average this device did, as ``×``.

    ``device self-sufficiency / house self-sufficiency``, both over the same
    period. 1.0 means the device took its energy at moments statistically
    indistinguishable from the house as a whole — which is exactly where a load
    that cannot be moved (a fridge, a router) lands, and correctly so: it is
    neither rewarded nor blamed. Above 1.0 it ran in the sun on purpose.

    The point of dividing by the house figure rather than reading the device
    percentage directly is seasonal comparability: 80% in January, when the
    house managed 20%, is a very different achievement from 80% in July, when
    the house managed 70%. The index says 4.0 and 1.14 respectively.
    """

    _attr_native_unit_of_measurement = "×"
    _attr_suggested_display_precision = DEFAULT_INDEX_PRECISION

    def __init__(self, hass: HomeAssistant, *, slug: str, device_percentage: str,
                 house_percentage: str, icon: str = "mdi:scale-balance",
                 visible: bool = True) -> None:
        super().__init__(hass, slug=slug, icon=icon, visible=visible,
                         sources=[device_percentage, house_percentage])
        self._device = device_percentage
        self._house = house_percentage

    @callback
    def _recalculate(self) -> None:
        device = _to_float((s := self.hass.states.get(self._device)) and s.state)
        house = _to_float((s := self.hass.states.get(self._house)) and s.state)
        if device is None or house is None or house <= 0:
            # A house baseline of zero (a winter night, a whole day of rain)
            # makes every device infinitely better than nothing: undefined, not
            # a record score.
            self._unavailable()
            return
        self._attr_available = True
        self._attr_native_value = round(device / house, 6)


class BaselineAdvantageSensor(_BaselineSensor):
    """Self-produced kWh this device captured *beyond* running at random times.

        advantage = from_self − (energy × house_baseline)

    The subtracted term is what the device would have picked up by drawing its
    energy in proportion to how the house drew its own — so what is left is the
    part attributable to *when* it ran, with the size of the appliance and the
    weather of that period both already accounted for.

    This is the quantity to rank by, for a reason the percentage cannot match:
    it is in kWh, so a 5 W lamp running entirely on sun scores near zero instead
    of topping the table, while a heat pump at a modest 40% outranks it by a
    wide margin — which is the honest ordering of who actually moved solar
    energy around.

    It is also **zero-sum**: summed over loads covering the whole house it
    cancels exactly, because the baseline *is* the house's energy-weighted mean.
    One appliance's surplus is another's deficit, which is what a ranking should
    be. The residue of the profiled devices is the unprofiled remainder of the
    house, and reading it as its own figure is often the most useful line of all.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_suggested_display_precision = 3

    def __init__(self, hass: HomeAssistant, *, slug: str, from_self: str, total: str,
                 house_percentage: str, icon: str = "mdi:sun-clock",
                 visible: bool = True) -> None:
        super().__init__(hass, slug=slug, icon=icon, visible=visible,
                         sources=[from_self, total, house_percentage])
        self._from_self = from_self
        self._total = total
        self._house = house_percentage

    @callback
    def _recalculate(self) -> None:
        from_self = _to_float((s := self.hass.states.get(self._from_self)) and s.state)
        total = _to_float((s := self.hass.states.get(self._total)) and s.state)
        house = _to_float((s := self.hass.states.get(self._house)) and s.state)
        if from_self is None or total is None or house is None:
            self._unavailable()
            return
        self._attr_available = True
        self._attr_native_value = round(from_self - total * (house / 100.0), 6)


class EnergyBalanceSensor(DeltaCombinationSensor):
    """Drift between the two readings of the self-consumed energy, in kWh.

    The house identity ``consumption = production + import − export`` gives
    ``E_self`` twice over, from two independent measurement chains::

        (consumption − import) − (production − export)  =  0

    Accumulated from deltas, so it starts at zero when the integration first
    sees the counters and stays there while the meters agree. **This is the
    entity that says whether to trust the others.** Steady drift means a
    measurement fault — a clamp on backwards, a production figure that counts
    something the consumption one does not, meters reading different sides of
    the same wire.

    Comparing the raw totals instead would be meaningless: they are lifetime
    counters started on different days, so their difference is mostly the gap
    between two installation dates.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 3

    def __init__(self, hass: HomeAssistant, *, slug: str, consumption: str,
                 grid_import: str, production: str, export: str,
                 icon: str = "mdi:scale-unbalanced") -> None:
        super().__init__(
            hass, slug=slug, icon=icon,
            # (C − I) − (P − E), expanded so each counter carries its own sign.
            terms={consumption: 1, grid_import: -1, production: -1, export: 1},
        )


def build_scored_periods(
    hass: HomeAssistant,
    device: dict,
    *,
    name_suffix: str,
    factory,
    unit: str,
    display_precision: int,
) -> list:
    """One score per configured period: a live sensor plus the meter that keeps it.

    A period score cannot be metered off the lifetime one. The value that
    belongs in a day's row is that day's *own* ratio, so each cycle gets its own
    live sensor reading that cycle's accumulators — hence ``factory(cycle,
    slug)`` and the per-cycle ``source`` below.

    The live sensors are registered but hidden. They exist to be metered: the
    Lean gauge carries the public name and writes exactly one long-term point
    per period, holding the value at close, which is the figure a period score
    means. Showing both would put two entities with the same number side by side
    in every picker.
    """
    prefix = device["prefix"]
    periods = device.get("periods") or ["daily", "monthly", "yearly"]

    entities: list = []
    for cycle in periods:
        live_slug = f"{prefix}_{name_suffix}_{cycle}_live"
        entities.append(factory(cycle, live_slug))

    entities += build_period_meters(
        hass, device,
        source=lambda cycle: f"sensor.{prefix}_{name_suffix}_{cycle}_live",
        name_suffix=name_suffix, unit=unit, device_class=None,
        net_consumption=True, absolute_values=True,
        display_precision=display_precision,
    )
    return entities
