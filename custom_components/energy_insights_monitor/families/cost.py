"""Family: cost.

Replaces the generator's ``001_basics/basics_003_[energy_cost]`` fragment.

Architecture:
- One live ``_energy_cost_lifetime`` integrator (€ accumulator, price-weighted on
  each energy delta) — see ..integrator.
- One Lean cost meter per cycle, sourced from that integrator, writing a single
  consolidated LTS row per cycle.

Requires a price entity (from the device or the shared defaults); without one the
family produces nothing.
"""

import logging

from homeassistant.components.sensor import SensorDeviceClass

from ..const import CONF_ENERGY, CONF_ENERGY_PRICE, CONF_POWER
from ..integrator import EnergyCostIntegratorSensor
from ..instant import INSTANT_COST_VARIANTS, InstantCostSensor
from ..lean import build_cycle_meters
from .energy import lifetime_entity_id

_LOGGER = logging.getLogger(__name__)


def build(hass, device):
    """Return the cost integrator plus its per-cycle Lean meters."""
    price = device.get(CONF_ENERGY_PRICE)
    if not price:
        _LOGGER.debug(
            "No energy_price for %s; skipping cost family", device["prefix"]
        )
        return []

    prefix = device["prefix"]
    lifetime_slug = f"{prefix}_energy_cost_lifetime"

    entities = [
        EnergyCostIntegratorSensor(
            hass,
            slug=lifetime_slug,
            # Integrate the decoupled lifetime's deltas (reset-free), not the raw hw
            # sensor, so cost stays consistent with the energy total on plug swaps.
            energy_source=lifetime_entity_id(prefix),
            price_source=price,
        )
    ]
    entities.extend(
        build_cycle_meters(
            hass,
            device,
            source=f"sensor.{lifetime_slug}",
            name_suffix="energy_cost",
            unit="€",
            device_class=SensorDeviceClass.MONETARY,
        )
    )

    # Instantaneous cost-rate projections (basics_004): power * price extrapolated.
    for suffix, unit, factor in INSTANT_COST_VARIANTS:
        entities.append(
            InstantCostSensor(
                hass,
                slug=f"{prefix}_energy_cost_instant_{suffix}",
                power_source=device[CONF_POWER],
                price_source=price,
                factor=factor,
                unit=unit,
            )
        )
    return entities
