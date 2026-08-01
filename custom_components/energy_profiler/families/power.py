"""Family: power — instantaneous power sensors.

Replaces the generator's power fragments (basics_001 + selfsufficiency_001):
peak power, and (when a self-sufficiency source exists) the self/grid split.
Always enabled — every device has a power sensor.
"""

from ..const import (
    CONF_BATTERY_SHARE_SOURCE,
    CONF_POWER,
    CONF_SELF_SUFFICIENCY_SOURCE,
    CONF_SOLAR_SHARE_SOURCE,
)
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
        # Second-level instantaneous split of the self share (solar vs battery),
        # mirroring the energy groups: whichever share the user provided drives
        # one side directly, the other side is its complement.
        solar_share = device.get(CONF_SOLAR_SHARE_SOURCE)
        battery_share = device.get(CONF_BATTERY_SHARE_SOURCE)
        share = solar_share or battery_share
        if share:
            entities += [
                PowerSplitSensor(
                    hass, slug=f"{prefix}_power_from_solar", power_source=power,
                    ratio_source=ratio, portion="self", icon="mdi:weather-sunny",
                    share_source=share, share_complement=bool(battery_share),
                ),
                PowerSplitSensor(
                    hass, slug=f"{prefix}_power_from_battery", power_source=power,
                    ratio_source=ratio, portion="self", icon="mdi:home-battery",
                    share_source=share, share_complement=bool(solar_share),
                ),
            ]
    return entities
