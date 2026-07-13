"""Family: standby.

Replaces the generator's ``004_standby`` fragments: the energy (and its cost)
drawn while the device is *not* running — idle/standby consumption.

The original measured this as ``hw_energy - cycle_stop_snapshot`` while idle. Here
a :class:`StandbyEnergyAccumulator` accumulates the energy deltas only while
``binary_sensor.<prefix>_running`` is off, which yields the same per-cycle standby
energy for the downstream Lean meters without depending on the cycle stop snapshot.

Requires the running detection (the cycles ``run`` block); if a device enables
standby without it, the family is skipped with a warning.
"""

import logging

from homeassistant.components.sensor import SensorDeviceClass

from ..const import CONF_ENERGY_PRICE, CONF_RUN
from ..integrator import EnergyCostIntegratorSensor
from ..lean import build_cycle_meters
from ..lifetime import StandbyEnergyAccumulator
from .cycles import running_entity_id
from .energy import lifetime_entity_id

_LOGGER = logging.getLogger(__name__)


def build(hass, device):
    """Return the standby energy accumulator, its Lean meters, and (if priced) cost."""
    prefix = device["prefix"]

    if not device.get(CONF_RUN):
        _LOGGER.warning(
            "Device %s enables standby but has no 'run' block; standby needs running "
            "detection to know when the device is idle — skipping standby family",
            prefix,
        )
        return []

    price = device.get(CONF_ENERGY_PRICE)
    standby_lifetime = f"{prefix}_standby_energy_lifetime"

    from ..cycles_tracker import StandbyDurationSensor

    entities = [
        StandbyEnergyAccumulator(
            hass,
            slug=standby_lifetime,
            # Gate the decoupled lifetime's deltas on the running state.
            energy_source=lifetime_entity_id(prefix),
            running_entity=running_entity_id(prefix),
        ),
        StandbyDurationSensor(
            hass, slug=f"{prefix}_standby_duration", running_entity=running_entity_id(prefix),
        ),
    ]
    entities += build_cycle_meters(
        hass, device,
        source=f"sensor.{standby_lifetime}",
        name_suffix="standby_energy",
        unit="kWh", device_class=SensorDeviceClass.ENERGY,
    )

    if price:
        standby_cost_lifetime = f"{prefix}_standby_energy_cost_lifetime"
        entities.append(
            EnergyCostIntegratorSensor(
                hass,
                slug=standby_cost_lifetime,
                energy_source=f"sensor.{standby_lifetime}",
                price_source=price,
                icon="mdi:cash-clock",
            )
        )
        entities += build_cycle_meters(
            hass, device,
            source=f"sensor.{standby_cost_lifetime}",
            name_suffix="standby_energy_cost",
            unit="€", device_class=SensorDeviceClass.MONETARY,
        )

    return entities
