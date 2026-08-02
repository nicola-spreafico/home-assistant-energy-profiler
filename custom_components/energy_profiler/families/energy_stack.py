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
    DEFAULT_COST_PRECISION,
    DEFAULT_PERCENTAGE_PRECISION,
)
from ..flows import resolve_flows
from ..instant import INSTANT_COST_PERIODS, InstantCostSensor, resolve_instant_periods
from ..integrator import EnergyCostIntegratorSensor
from ..lean import build_period_meters
from ..lifetime import EnergyLifetimeSensor, GatedEnergyAccumulator
from ..split import EnergyFlowSplitter, EnergyRatioSensor, SplitPortionSensor

ICON_SELF = "mdi:solar-panel"
ICON_GRID = "mdi:transmission-tower"
ICON_SOLAR = "mdi:weather-sunny"
ICON_BATTERY = "mdi:home-battery"
ICON_SAVINGS = "mdi:piggy-bank"
ICON_GRID_COST = "mdi:cash-minus"

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

    # Percentage views: live ratios, each consolidated to one LTS gauge point per
    # period (absolute_values + net_consumption: a gauge, not a cumulative sum).
    #
    # Every one of them divides two *accumulators*, never averages instantaneous
    # percentages: a closed period meter therefore reads the energy-weighted
    # share of that period, which is the number "how much of yesterday was sun"
    # actually asks for.
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
            ratio_lifetime = f"{base}_{suffix}_lifetime"
            entities.append(
                EnergyRatioSensor(
                    hass, slug=ratio_lifetime,
                    numerator=f"sensor.{base}_{portion}_lifetime",
                    denominator=f"sensor.{lifetime_slug}",
                    icon=icon,
                )
            )
            entities += build_period_meters(
                hass, device, source=f"sensor.{ratio_lifetime}",
                name_suffix=f"{name_base}_{suffix}", unit="%", device_class=None,
                net_consumption=True, absolute_values=True,
                display_precision=DEFAULT_PERCENTAGE_PRECISION,
            )

    return entities
