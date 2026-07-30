"""Centralized energy stack — the sensor block every energy group exposes.

A *group* is a gated view of the device's consumption: all of it (``energy``),
only while running (``running_energy``) or only in standby (``standby_energy``).
Symmetry by construction: every group exposes the SAME block, so distinguishing
running vs standby consumption never costs you the solar split or the cost view.
Per group ``<base>`` (= ``<prefix>_<name_base>``), permuted over the configured
periods:

- ``<base>_lifetime`` + ``<base>_<period>``            kWh accumulator + meters
- ``<base>_from_self`` / ``_from_grid`` (+ meters)     self/grid split     [needs self_sufficiency_source]
- ``<base>_from_solar`` / ``_from_battery`` (+ meters) self split in two   [needs solar_share_source or battery_share_source]
- ``<base>_cost`` (+ meters)                           € at consumption    [needs energy_price]
- ``<base>_from_grid_savings`` / ``_from_grid_cost``   € views of the split [needs both]
- ``<base>_self_sufficiency`` (+ gauge meters)         live % ratio        [needs self_sufficiency_source]

The total group additionally gets the instantaneous cost projections
(``<base>_cost_instant_*`` and, with a self-sufficiency source,
``<base>_cost_instant_from_grid_*``), one per instant period: the device's
``instant_periods:`` when set, otherwise its ``periods:``. The gated groups
source the *decoupled* total lifetime, so every group inherits the
reset/plug-swap protection.
"""

from homeassistant.components.sensor import SensorDeviceClass

from ..const import (
    CONF_BATTERY_SHARE_SOURCE,
    CONF_COST_PRECISION,
    CONF_ENERGY_PRICE,
    CONF_POWER,
    CONF_SELF_SUFFICIENCY_SOURCE,
    CONF_SOLAR_SHARE_SOURCE,
    DEFAULT_COST_PRECISION,
    DEFAULT_PERCENTAGE_PRECISION,
)
from ..instant import INSTANT_COST_PERIODS, InstantCostSensor, resolve_instant_periods
from ..integrator import EnergyCostIntegratorSensor
from ..lean import build_period_meters
from ..lifetime import EnergyLifetimeSensor, GatedEnergyAccumulator
from ..split import EnergyBalancerSensor, SplitPartnerSensor, SelfSufficiencyRatioSensor

ICON_SELF = "mdi:solar-panel"
ICON_GRID = "mdi:transmission-tower"
ICON_SOLAR = "mdi:weather-sunny"
ICON_BATTERY = "mdi:home-battery"
ICON_SAVINGS = "mdi:piggy-bank"
ICON_GRID_COST = "mdi:cash-minus"


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
    ratio = device.get(CONF_SELF_SUFFICIENCY_SOURCE)
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

    # Solar/grid split: the balancer owns the single atomic split of the group
    # lifetime's deltas and pushes the exact remainder to the passive partner,
    # so from_self + from_grid == the group total, always. Gating is inherited:
    # the source only moves while the gate is open.
    if ratio:
        from_self_lifetime = f"{base}_from_self_lifetime"
        from_grid_lifetime = f"{base}_from_grid_lifetime"
        from_grid = SplitPartnerSensor(hass, slug=from_grid_lifetime, icon=ICON_GRID)
        from_self = EnergyBalancerSensor(
            hass,
            slug=from_self_lifetime,
            energy_source=f"sensor.{lifetime_slug}",
            ratio_source=ratio,
            partner=from_grid,
            icon=ICON_SELF,
        )
        entities += [from_self, from_grid]
        entities += build_period_meters(
            hass, device, source=f"sensor.{from_self_lifetime}",
            name_suffix=f"{name_base}_from_self", unit="kWh", device_class=ENERGY,
        )
        entities += build_period_meters(
            hass, device, source=f"sensor.{from_grid_lifetime}",
            name_suffix=f"{name_base}_from_grid", unit="kWh", device_class=ENERGY,
        )

        # Optional second-level split of the self share: solar vs battery.
        # Same balancer mechanism, one level down: from_self's deltas are split
        # by the share %, so from_solar + from_battery == from_self, always.
        # The user provides either the solar or the battery share — whichever
        # they gave becomes the balancer, the other side is the exact remainder.
        solar_share = device.get(CONF_SOLAR_SHARE_SOURCE)
        battery_share = device.get(CONF_BATTERY_SHARE_SOURCE)
        if solar_share or battery_share:
            from_solar_lifetime = f"{base}_from_solar_lifetime"
            from_battery_lifetime = f"{base}_from_battery_lifetime"
            if solar_share:
                partner = SplitPartnerSensor(hass, slug=from_battery_lifetime, icon=ICON_BATTERY)
                balancer = EnergyBalancerSensor(
                    hass, slug=from_solar_lifetime,
                    energy_source=f"sensor.{from_self_lifetime}",
                    ratio_source=solar_share, partner=partner, icon=ICON_SOLAR,
                )
            else:
                partner = SplitPartnerSensor(hass, slug=from_solar_lifetime, icon=ICON_SOLAR)
                balancer = EnergyBalancerSensor(
                    hass, slug=from_battery_lifetime,
                    energy_source=f"sensor.{from_self_lifetime}",
                    ratio_source=battery_share, partner=partner, icon=ICON_BATTERY,
                )
            entities += [balancer, partner]
            entities += build_period_meters(
                hass, device, source=f"sensor.{from_solar_lifetime}",
                name_suffix=f"{name_base}_from_solar", unit="kWh", device_class=ENERGY,
            )
            entities += build_period_meters(
                hass, device, source=f"sensor.{from_battery_lifetime}",
                name_suffix=f"{name_base}_from_battery", unit="kWh", device_class=ENERGY,
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

    # Monetary views of the split.
    if price and ratio:
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

    # Self-sufficiency %: a live ratio, consolidated to one LTS gauge point per
    # period (absolute_values + net_consumption: a gauge, not a cumulative sum).
    if ratio:
        ss_lifetime = f"{base}_self_sufficiency_lifetime"
        entities.append(
            SelfSufficiencyRatioSensor(
                hass, slug=ss_lifetime,
                numerator=f"sensor.{base}_from_self_lifetime",
                denominator=f"sensor.{lifetime_slug}",
            )
        )
        entities += build_period_meters(
            hass, device, source=f"sensor.{ss_lifetime}",
            name_suffix=f"{name_base}_self_sufficiency", unit="%", device_class=None,
            net_consumption=True, absolute_values=True,
            display_precision=DEFAULT_PERCENTAGE_PRECISION,
        )

    return entities
