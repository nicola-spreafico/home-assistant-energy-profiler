"""Family: power — instantaneous power sensors.

Replaces the generator's power fragments (basics_001 + selfsufficiency_001):
peak power, and (when a self-sufficiency source exists) the self/grid split.
Always enabled — every device has a power sensor.
"""

from ..const import CONF_POWER, CONF_SELF_SUFFICIENCY_SOURCE
from ..power import PowerMaxSensor, PowerSplitSensor


def build(hass, device):
    prefix = device["prefix"]
    power = device[CONF_POWER]
    ratio = device.get(CONF_SELF_SUFFICIENCY_SOURCE)

    entities = [PowerMaxSensor(hass, slug=f"{prefix}_power_max", power_source=power)]
    if ratio:
        entities += [
            PowerSplitSensor(
                hass, slug=f"{prefix}_power_from_self", power_source=power,
                ratio_source=ratio, portion="self", icon="mdi:solar-power",
            ),
            PowerSplitSensor(
                hass, slug=f"{prefix}_power_from_grid", power_source=power,
                ratio_source=ratio, portion="grid", icon="mdi:transmission-tower",
            ),
        ]
    return entities
