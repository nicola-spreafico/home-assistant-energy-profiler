"""Centralized energy stack — the sensor block every energy group exposes.

A *group* is a gated view of the device's consumption: all of it (``energy``),
only while running (``running_energy``) or only in standby (``standby_energy``).
Symmetry by construction: every group exposes the SAME block, so distinguishing
running vs standby consumption never costs you the solar split or the cost view.
Per group ``<base>`` (= ``<prefix>_<name_base>``), permuted over the configured
periods:

- ``<base>_lifetime`` + ``<base>_<period>``            kWh accumulator + meters
- ``<base>_from_self`` / ``_from_grid`` (+ meters)     self/grid split     [needs power_flows]
- ``<base>_from_solar`` / ``_from_battery`` (+ meters) one per declared channel
- ``<base>_cost`` (+ meters)                           € at consumption    [needs energy_price]
- ``<base>_from_grid_savings`` / ``_from_grid_cost``   € views of the split [needs both]
- ``<base>_from_*_percentage`` (+ gauge meters)          each portion's % of the group total
- ``<base>_from_*_percentage`` (+ gauge meters)        each portion's % of the total

``from_self`` is kept even when a single channel makes it numerically identical
to that channel: aggregate "what did not come from the grid" is the quantity the
monetary view prices, and the one analytics ask for when the source does not
matter. The per-portion percentages, by contrast, are only created where they
say something new — with one channel, its percentage *is* self-sufficiency.

The total group additionally gets the instantaneous cost projections
(``<base>_cost_instant_*`` and, with house flows configured,
``<base>_cost_instant_from_grid_*``), one per instant period: the device's
``instant_periods:`` when set, otherwise its ``periods:``. The gated groups
source the *decoupled* total lifetime, so every group inherits the
reset/plug-swap protection.
"""

from homeassistant.components.sensor import SensorDeviceClass

from ..const import (
    CONF_COST_PRECISION,
    CONF_ENERGY_PRICE,
    CONF_FLOW_BATTERY,
    CONF_FLOW_SOLAR,
    CONF_POWER,
    CONF_INCLUDE_IN_RANKING,
    DEFAULT_COST_PRECISION,
    DEFAULT_INDEX_PRECISION,
    DEFAULT_PERCENTAGE_PRECISION,
)
from ..flows import resolve_flows
from ..house import baseline_entity
from ..instant import INSTANT_COST_PERIODS, InstantCostSensor, resolve_instant_periods
from ..integrator import EnergyCostIntegratorSensor
from ..lean import build_period_meters
from ..lifetime import EnergyLifetimeSensor, GatedEnergyAccumulator
from ..scores import (
    BaselineAdvantageSensor,
    BaselineIndexSensor,
    build_scored_periods,
)
from ..split import EnergyFlowSplitter, EnergyRatioSensor, SplitPortionSensor

ICON_SELF = "mdi:solar-panel"
ICON_GRID = "mdi:transmission-tower"
ICON_SOLAR = "mdi:weather-sunny"
ICON_BATTERY = "mdi:home-battery"
ICON_SAVINGS = "mdi:piggy-bank"
ICON_GRID_COST = "mdi:cash-minus"
ICON_INDEX = "mdi:scale-balance"
ICON_ADVANTAGE = "mdi:sun-clock"

_CHANNEL_ICONS = {CONF_FLOW_SOLAR: ICON_SOLAR, CONF_FLOW_BATTERY: ICON_BATTERY}


def build_stack(
    hass,
    device,
    *,
    name_base: str,
    source: str,
    gate_entity: str | None = None,
    include_instant: bool = False,
) -> list:
    """Build one energy group: base accumulator, split, costs, %, period meters.

    ``name_base`` names the group (``energy``, ``running_energy``,
    ``standby_energy``) and prefixes every slug; ``source`` is the entity whose
    positive deltas are accumulated; ``gate_entity`` restricts accumulation to
    while that binary sensor is on (None = always, the total group).
    """
    prefix = device["prefix"]
    base = f"{prefix}_{name_base}"
    price = device.get(CONF_ENERGY_PRICE)
    flows = resolve_flows(device)
    cost_precision = device.get(CONF_COST_PRECISION, DEFAULT_COST_PRECISION)
    instant_periods = resolve_instant_periods(device) if include_instant else []
    ENERGY = SensorDeviceClass.ENERGY
    MONEY = SensorDeviceClass.MONETARY

    lifetime_slug = f"{base}_lifetime"
    if gate_entity is None:
        accumulator = EnergyLifetimeSensor(hass, slug=lifetime_slug, energy_source=source)
    else:
        accumulator = GatedEnergyAccumulator(
            hass, slug=lifetime_slug, energy_source=source, gate_entity=gate_entity
        )
    entities: list = [accumulator]
    entities += build_period_meters(
        hass, device, source=f"sensor.{lifetime_slug}",
        name_suffix=name_base, unit="kWh", device_class=ENERGY,
    )

    # Grid/self/channel split: one splitter owns the single atomic attribution of
    # the group lifetime's deltas and pushes exact remainders into the passive
    # portions, so from_self + from_grid == the group total and (with two
    # channels) from_solar + from_battery == from_self, always. Gating is
    # inherited: the source only moves while the gate is open.
    if flows is not None:
        from_self_lifetime = f"{base}_from_self_lifetime"
        from_grid_lifetime = f"{base}_from_grid_lifetime"
        from_grid = SplitPortionSensor(hass, slug=from_grid_lifetime, icon=ICON_GRID)
        channel_portions = {
            channel: SplitPortionSensor(
                hass, slug=f"{base}_from_{channel}_lifetime", icon=_CHANNEL_ICONS[channel]
            )
            for channel in flows["channels"]
        }
        from_self = EnergyFlowSplitter(
            hass,
            slug=from_self_lifetime,
            energy_source=f"sensor.{lifetime_slug}",
            flows=flows,
            grid_portion=from_grid,
            channel_portions=channel_portions,
            icon=ICON_SELF,
        )
        entities += [from_self, from_grid, *channel_portions.values()]
        for portion in ("from_self", "from_grid", *(
            f"from_{channel}" for channel in flows["channels"]
        )):
            entities += build_period_meters(
                hass, device, source=f"sensor.{base}_{portion}_lifetime",
                name_suffix=f"{name_base}_{portion}", unit="kWh", device_class=ENERGY,
            )

    # Cost: each delta priced at the tariff valid at that moment.
    if price:
        cost_lifetime = f"{base}_cost_lifetime"
        entities.append(
            EnergyCostIntegratorSensor(
                hass, slug=cost_lifetime,
                energy_source=f"sensor.{lifetime_slug}", price_source=price,
                display_precision=cost_precision,
            )
        )
        entities += build_period_meters(
            hass, device, source=f"sensor.{cost_lifetime}",
            name_suffix=f"{name_base}_cost", unit="€", device_class=MONEY,
            display_precision=cost_precision,
        )
        # Instantaneous cost-rate projections (power × price): total group only —
        # they read the raw power sensor, which no gate applies to. One variant per
        # instant period (``instant_periods:``, else the device's ``periods:``).
        if include_instant:
            for period in instant_periods:
                unit, factor = INSTANT_COST_PERIODS[period]
                entities.append(
                    InstantCostSensor(
                        hass, slug=f"{base}_cost_instant_{period}",
                        power_source=device[CONF_POWER], price_source=price,
                        factor=factor, unit=unit,
                    )
                )

    # Monetary views of the split. They sit on the self/grid boundary because
    # that is where money changes hands: solar and battery both cost nothing, so
    # splitting savings between them would be two entities saying one thing.
    if price and flows is not None:
        savings_lifetime = f"{base}_from_grid_savings_lifetime"
        grid_cost_lifetime = f"{base}_from_grid_cost_lifetime"
        entities += [
            EnergyCostIntegratorSensor(
                hass, slug=savings_lifetime,
                energy_source=f"sensor.{base}_from_self_lifetime",
                price_source=price, icon=ICON_SAVINGS,
                display_precision=cost_precision,
            ),
            EnergyCostIntegratorSensor(
                hass, slug=grid_cost_lifetime,
                energy_source=f"sensor.{base}_from_grid_lifetime",
                price_source=price, icon=ICON_GRID_COST,
                display_precision=cost_precision,
            ),
        ]
        entities += build_period_meters(
            hass, device, source=f"sensor.{savings_lifetime}",
            name_suffix=f"{name_base}_from_grid_savings", unit="€", device_class=MONEY,
            display_precision=cost_precision,
        )
        entities += build_period_meters(
            hass, device, source=f"sensor.{grid_cost_lifetime}",
            name_suffix=f"{name_base}_from_grid_cost", unit="€", device_class=MONEY,
            display_precision=cost_precision,
        )
        # Grid-only counterpart of the instantaneous projections above. Same sensor,
        # fed the *grid share* of the draw instead of the whole of it, so it answers
        # "what is this actually costing me right now" once self-production is
        # netted off. The qualifier trails ``cost_instant`` (rather than sitting in
        # the canonical ``_from_grid_`` slot) to keep the eight projections sorting
        # as one family in the UI.
        if include_instant:
            for period in instant_periods:
                unit, factor = INSTANT_COST_PERIODS[period]
                entities.append(
                    InstantCostSensor(
                        hass, slug=f"{base}_cost_instant_from_grid_{period}",
                        power_source=f"sensor.{prefix}_power_from_grid",
                        price_source=price, factor=factor, unit=unit,
                        icon=ICON_GRID_COST,
                    )
                )

    # Percentage views. Every one divides two *accumulators*, never averages
    # instantaneous percentages — the two differ by cov(power, share)/mean(power),
    # which is precisely the "ran while the sun was up" signal being measured.
    #
    # Each period divides *that period's* two meters, not the lifetime pair: a
    # day's figure has to be built from the day's energies, or a device that ran
    # at noon and one that ran at 3am produce nearly the same number once a few
    # months of lifetime totals have accumulated behind them. The live sensors
    # are hidden and exist to be metered; the Lean gauge keeps the public name
    # and writes one long-term point per period, holding the closing value.
    if flows is not None:
        ratios = [(f"from_{p}_percentage", f"from_{p}", i) for p, i in (("self", ICON_SELF), ("grid", ICON_GRID))]
        # Per-channel percentages only where they say something new: with a
        # single channel, that channel is the whole self share and its
        # percentage would be a second copy of self-sufficiency.
        if len(flows["channels"]) > 1:
            ratios += [
                (f"from_{channel}_percentage", f"from_{channel}", _CHANNEL_ICONS[channel])
                for channel in flows["channels"]
            ]

        for suffix, portion, icon in ratios:
            entities.append(
                EnergyRatioSensor(
                    hass, slug=f"{base}_{suffix}_lifetime",
                    numerator=f"sensor.{base}_{portion}_lifetime",
                    denominator=f"sensor.{lifetime_slug}",
                    icon=icon,
                )
            )
            entities += build_scored_periods(
                hass, device, name_suffix=f"{name_base}_{suffix}",
                unit="%", display_precision=DEFAULT_PERCENTAGE_PRECISION,
                factory=lambda cycle, slug, portion=portion, icon=icon: EnergyRatioSensor(
                    hass, slug=slug,
                    numerator=f"sensor.{base}_{portion}_{cycle}",
                    denominator=f"sensor.{prefix}_{name_base}_{cycle}",
                    icon=icon, visible=False,
                ),
            )

    # How this device did against the house over the same period. Needs the
    # house baseline, so it is built only where `energy_flows:` is declared —
    # and only on the total group: "did the washing machine run in the sun" is
    # one question, and asking it again of its standby draw is not a second one.
    if (
        flows is not None
        and include_instant
        and device.get("has_baseline")
        and device.get(CONF_INCLUDE_IN_RANKING, True)
    ):
        entities += _baseline_views(hass, device, base=base, name_base=name_base)

    return entities


def _baseline_views(hass, device, *, base: str, name_base: str) -> list:
    """The two ways of reading this device against the house: index and advantage.

    Both compare like with like — the device's period against the house's *same*
    period — because the achievable figure moves with the season. 80% self-fed
    in January, when the house managed 20%, is four times the house; the same
    80% in July, when the house managed 70%, is barely above it.

    ``index`` is the readable one: 1.0 means the device drew at moments
    statistically indistinguishable from the house as a whole, which is exactly
    where a load that cannot be moved belongs — neither rewarded nor blamed.

    ``advantage`` is the rankable one: the same comparison in kWh, so it weighs
    how much energy the device actually moved and not only how well it timed it.
    A 5 W lamp on a sunny windowsill scores a spectacular index and an advantage
    of nothing, which is the honest reading of both. See scores.py.
    """
    prefix = device["prefix"]
    entities = build_scored_periods(
        hass, device, name_suffix=f"{name_base}_from_self_index",
        unit="×", display_precision=DEFAULT_INDEX_PRECISION,
        factory=lambda cycle, slug: BaselineIndexSensor(
            hass, slug=slug,
            device_percentage=f"sensor.{base}_from_self_percentage_{cycle}",
            house_percentage=baseline_entity(cycle),
            icon=ICON_INDEX, visible=False,
        ),
    )
    entities += build_scored_periods(
        hass, device, name_suffix=f"{name_base}_from_self_advantage",
        unit="kWh", display_precision=3,
        factory=lambda cycle, slug: BaselineAdvantageSensor(
            hass, slug=slug,
            from_self=f"sensor.{base}_from_self_{cycle}",
            total=f"sensor.{prefix}_{name_base}_{cycle}",
            house_percentage=baseline_entity(cycle),
            icon=ICON_ADVANTAGE, visible=False,
        ),
    )
    return entities
