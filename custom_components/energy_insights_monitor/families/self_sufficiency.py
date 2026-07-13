"""Family: self_sufficiency.

Replaces the generator's ``002_selfsufficiency`` fragments (except the raw power
split 001, which is instantaneous and not meter-like).

Per device it builds, when a self-sufficiency percentage source is configured:
- two lifetime split accumulators: energy_from_self / energy_from_grid (kWh);
- per-cycle Lean meters over each (from_self, from_grid);
- when a price is available: savings (self-produced € not spent) and grid cost
  (€ paid for imports) lifetimes + their per-cycle Lean meters;
- live self-sufficiency % sensors per cycle.

DEFERRED (flagged in the migration plan for pilot validation): consolidating the
self-sufficiency **percentages** into one LTS row per cycle. Percentages are a
mean-type series (not a cumulative sum), so the Lean cycle-meter approach does not
apply unchanged. For now the live % sensors above record as standard measurement
series; the LTS-consolidation strategy (e.g. absolute_values + end-of-period
snapshot) is left for the pilot.
"""

import logging

from homeassistant.components.sensor import SensorDeviceClass

from ..const import CONF_ENERGY_PRICE, CONF_SELF_SUFFICIENCY_SOURCE
from ..integrator import EnergyCostIntegratorSensor
from ..lean import build_cycle_meters
from ..split import EnergyBalancerSensor, SplitPartnerSensor, SelfSufficiencyRatioSensor
from .energy import lifetime_entity_id

_LOGGER = logging.getLogger(__name__)

ICON_SELF = "mdi:solar-panel"
ICON_GRID = "mdi:transmission-tower"
ICON_SAVINGS = "mdi:piggy-bank"
ICON_GRID_COST = "mdi:cash-minus"


def build(hass, device):
    """Return the self-sufficiency entities for a resolved device."""
    ratio_source = device.get(CONF_SELF_SUFFICIENCY_SOURCE)
    if not ratio_source:
        return []

    prefix = device["prefix"]
    price = device.get(CONF_ENERGY_PRICE)
    cycles = device.get("cycles") or ["daily", "monthly", "yearly"]

    from_self_lifetime = f"{prefix}_energy_from_self_lifetime"
    from_grid_lifetime = f"{prefix}_energy_from_grid_lifetime"

    # Grid partner is passive; the balancer owns the single atomic split and pushes
    # the exact remainder to it, so from_self + from_grid == total consumed, always.
    from_grid = SplitPartnerSensor(hass, slug=from_grid_lifetime, icon=ICON_GRID)
    from_self = EnergyBalancerSensor(
        hass,
        slug=from_self_lifetime,
        # Split the decoupled lifetime's deltas (reset-free) so from_self + from_grid
        # stays equal to the energy total across hw sensor changes.
        energy_source=lifetime_entity_id(prefix),
        ratio_source=ratio_source,
        partner=from_grid,
        icon=ICON_SELF,
    )
    entities = [from_self, from_grid]

    entities += build_cycle_meters(
        hass, device,
        source=f"sensor.{from_self_lifetime}",
        name_suffix="energy_from_self",
        unit="kWh", device_class=SensorDeviceClass.ENERGY,
    )
    entities += build_cycle_meters(
        hass, device,
        source=f"sensor.{from_grid_lifetime}",
        name_suffix="energy_from_grid",
        unit="kWh", device_class=SensorDeviceClass.ENERGY,
    )

    # Monetary families require a price entity.
    if price:
        savings_lifetime = f"{prefix}_energy_from_grid_savings_lifetime"
        grid_cost_lifetime = f"{prefix}_energy_from_grid_cost_lifetime"
        entities += [
            # Savings = value of self-produced energy (delta of from_self * price).
            EnergyCostIntegratorSensor(
                hass,
                slug=savings_lifetime,
                energy_source=f"sensor.{from_self_lifetime}",
                price_source=price,
                icon=ICON_SAVINGS,
            ),
            # Grid cost = € paid for imports (delta of from_grid * price).
            EnergyCostIntegratorSensor(
                hass,
                slug=grid_cost_lifetime,
                energy_source=f"sensor.{from_grid_lifetime}",
                price_source=price,
                icon=ICON_GRID_COST,
            ),
        ]
        entities += build_cycle_meters(
            hass, device,
            source=f"sensor.{savings_lifetime}",
            name_suffix="energy_from_grid_savings",
            unit="€", device_class=SensorDeviceClass.MONETARY,
        )
        entities += build_cycle_meters(
            hass, device,
            source=f"sensor.{grid_cost_lifetime}",
            name_suffix="energy_from_grid_cost",
            unit="€", device_class=SensorDeviceClass.MONETARY,
        )

    # Self-sufficiency %: a live lifetime ratio, consolidated to one LTS point per
    # cycle by Lean meters in absolute_values mode (they snapshot the % at each
    # period close — the % is a gauge, not a cumulative total). net_consumption lets
    # it move up and down. NOTE: the end-of-period snapshot timing for percentages is
    # the item flagged for pilot validation.
    ss_lifetime = f"{prefix}_energy_self_sufficiency_lifetime"
    entities.append(
        SelfSufficiencyRatioSensor(
            hass,
            slug=ss_lifetime,
            numerator=f"sensor.{from_self_lifetime}",
            denominator=lifetime_entity_id(prefix),
        )
    )
    entities += build_cycle_meters(
        hass, device,
        source=f"sensor.{ss_lifetime}",
        name_suffix="energy_self_sufficiency",
        unit="%", device_class=None,
        net_consumption=True, absolute_values=True,
    )

    return entities
