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

from ..const import CONF_ENERGY, CONF_ENERGY_PRICE
from ..integrator import EnergyCostIntegratorSensor
from ..lean import build_cycle_meters

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
            energy_source=device[CONF_ENERGY],
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
    return entities
