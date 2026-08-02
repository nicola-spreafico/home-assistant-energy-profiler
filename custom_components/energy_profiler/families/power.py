"""Family: power — instantaneous power sensors.

Replaces the generator's power fragments (basics_001 + selfsufficiency_001):
peak power, and (when the house flows are configured) the split of the draw.
Always enabled — every device has a power sensor.
"""

from ..const import CONF_FLOW_BATTERY, CONF_FLOW_GRID, CONF_FLOW_SOLAR, CONF_POWER
from ..flows import resolve_flows
from ..power import PowerMaxSensor, PowerSplitSensor

_CHANNEL_ICONS = {
    CONF_FLOW_SOLAR: "mdi:weather-sunny",
    CONF_FLOW_BATTERY: "mdi:home-battery",
}


def build(hass, device):
    prefix = device["prefix"]
    power = device[CONF_POWER]

    entities = [PowerMaxSensor(hass, slug=f"{prefix}_power_max", power_source=power)]

    flows = resolve_flows(device)
    if flows is None:
        return entities

    # self/grid always: the two sides of the split that exists whenever flows do.
    entities += [
        PowerSplitSensor(
            hass, slug=f"{prefix}_power_from_self", power_source=power,
            flows=flows, portion="self", icon="mdi:solar-power",
        ),
        PowerSplitSensor(
            hass, slug=f"{prefix}_power_from_grid", power_source=power,
            flows=flows, portion=CONF_FLOW_GRID, icon="mdi:transmission-tower",
        ),
    ]
    # One sensor per declared channel. With a single channel it carries the whole
    # self share — same number as `from_self`, but named for what it actually is.
    entities += [
        PowerSplitSensor(
            hass, slug=f"{prefix}_power_from_{channel}", power_source=power,
            flows=flows, portion=channel, icon=_CHANNEL_ICONS[channel],
        )
        for channel in flows["channels"]
    ]
    return entities
