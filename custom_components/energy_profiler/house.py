"""Prosumption: the house scored against itself, period by period.

Level 3 answers *"how much of what this appliance used came from my own
production?"*. That question only ever looks at the load side, which is why it
can be asked per device. This module asks the two questions that look at the
**generation** side, and they exist here and nowhere else because production
cannot be handed to an appliance (see energy_flows.py for why the attempt is not
approximate but degenerate).

One quantity, two denominators
------------------------------
The house obeys ``consumption = production + import − export``, so::

    E_self  =  consumption − import  =  production − export

The energy you self-supplied and the energy you self-consumed are **the same
kWh**, counted from opposite ends. What differs is what you divide it by::

    self-sufficiency = E_self / consumption     "did I cover my needs?"
    self-consumption = E_self / production      "did my production find a use?"
    prosumption      = E_self / min(the two)    "did the two meet in time?"

Each of the first two is capped by the other side. In winter, production below
consumption puts a hard ceiling of ``production/consumption`` on
self-sufficiency: 30% may be everything that was achievable, and reading it as a
failure is reading the size of the roof, not the behaviour of the house. In
summer the same is true of self-consumption in reverse — a low figure then means
there was nothing left to consume, not that anything was wasted.

Prosumption divides by whichever side was actually scarce, so it removes the
sizing of *both* sides and leaves only the overlap in time. It reaches 100% when
every kWh that could physically have been coupled was coupled, and its
complement is the only genuine waste: energy that existed and demand that
existed, which failed to meet because of the hour of the day. That is also the
only one of the three you can change tomorrow without buying anything — and, as
the house baseline, it is what every per-device comparison is scored against.
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant

from .const import (
    CONF_EFLOW_CONSUMPTION,
    CONF_EFLOW_EXPORT,
    CONF_EFLOW_IMPORT,
    CONF_EFLOW_PRODUCTION,
    CONF_LIVE_UPDATE_INTERVAL,
    CONF_PERIODS,
    DEFAULT_PERCENTAGE_PRECISION,
    DEFAULT_PERIODS,
    SYSTEM_PREFIX,
)
from .lean import build_period_meters
from .scores import (
    DeltaCombinationSensor,
    EnergyBalanceSensor,
    MinDenominatorRatioSensor,
    SelfEnergySensor,
    build_scored_periods,
)
from .split import EnergyRatioSensor

_LOGGER = logging.getLogger(__name__)

ICON_SELF = "mdi:solar-power-variant"
ICON_SUFFICIENCY = "mdi:home-lightning-bolt"
ICON_CONSUMPTION = "mdi:solar-panel"
ICON_PROSUMPTION = "mdi:sync"
ICON_HOUSE = "mdi:home-lightning-bolt-outline"
ICON_PRODUCTION = "mdi:weather-sunny"

# The name every per-device comparison divides by. Kept here so the device stack
# and the ranking cannot drift from what the house actually publishes.
BASELINE_SLUG = f"{SYSTEM_PREFIX}_self_sufficiency_percentage"


def baseline_entity(cycle: str) -> str:
    """The house self-sufficiency for one cycle: the per-device baseline."""
    return f"sensor.{BASELINE_SLUG}_{cycle}"


def system_meter_device(defaults: dict) -> dict:
    """A device-shaped dict so the house can reuse the per-device meter builder.

    The house is not a profiled appliance, but it wants the same period meters
    on the same configured cycles. Rather than a parallel implementation that
    would drift, it borrows the two keys ``build_period_meters`` reads.
    """
    return {
        "prefix": SYSTEM_PREFIX,
        "periods": defaults.get(CONF_PERIODS) or DEFAULT_PERIODS,
        "live_update_interval": defaults.get(CONF_LIVE_UPDATE_INTERVAL),
    }


def build(hass: HomeAssistant, defaults: dict, flows: dict) -> list:
    """Build the house prosumption block from resolved ``energy_flows``."""
    device = system_meter_device(defaults)
    consumption = flows[CONF_EFLOW_CONSUMPTION]
    grid_import = flows[CONF_EFLOW_IMPORT]
    production = flows[CONF_EFLOW_PRODUCTION]

    self_lifetime = f"{SYSTEM_PREFIX}_self_energy_lifetime"
    entities: list = [
        SelfEnergySensor(
            hass, slug=self_lifetime,
            consumption=consumption, grid_import=grid_import, icon=ICON_SELF,
        )
    ]
    # net_consumption: the self-consumed total dips whenever the import meter
    # ticks a moment before the consumption one, and a meter that discarded
    # those would drift upward by exactly the noise between the two readings.
    entities += build_period_meters(
        hass, device, source=f"sensor.{self_lifetime}",
        name_suffix="self_energy", unit="kWh", device_class=SensorDeviceClass.ENERGY,
        net_consumption=True,
    )

    # The denominators get their own accumulators rather than being read off the
    # declared counters directly. `lifetime` here has to mean "since this
    # integration started watching", and the declared counters do not: they were
    # started whenever each meter was installed, often years apart. Dividing a
    # from-zero numerator by an all-time denominator yields a lifetime score
    # that reads as ~0 and stays there — arithmetically fine, and meaningless.
    #
    # Anchoring both sides at the same moment fixes that, and costs nothing for
    # the period meters, which measure a delta over their window either way.
    # Production is machinery, consumption is a reading. Both are needed as
    # denominators, but production echoes a counter the user declared and has
    # nothing to add to it — the same reason `HouseFlowPowerSensor` is built
    # only for the *derived* contribution and never for a declared flow. So it
    # is registered and works, and stays off the device page.
    denominators: dict[str, str] = {}
    for key, source, visible in (
        ("consumption", consumption, True),
        ("production", production, False),
    ):
        if source is None:
            continue
        slug = f"{SYSTEM_PREFIX}_{key}_lifetime"
        denominators[key] = slug
        entities.append(
            DeltaCombinationSensor(
                hass, slug=slug, terms={source: 1}, visible=visible,
                icon=ICON_HOUSE if key == "consumption" else ICON_PRODUCTION,
            )
        )
        entities += build_period_meters(
            hass, device, source=f"sensor.{slug}",
            name_suffix=key, unit="kWh", device_class=SensorDeviceClass.ENERGY,
            hidden=not visible,
        )

    entities += _scores(hass, device, self_lifetime, denominators)

    if flows["has_balance"]:
        entities.append(
            EnergyBalanceSensor(
                hass, slug=f"{SYSTEM_PREFIX}_energy_balance",
                consumption=consumption, grid_import=grid_import,
                production=production, export=flows[CONF_EFLOW_EXPORT],
            )
        )
    return entities


def _scores(hass, device, self_lifetime: str, denominators: dict[str, str]) -> list:
    """The three percentages, each as a lifetime reading plus one per period.

    Every ratio divides two quantities anchored at the same moment: the
    ``lifetime`` ones two accumulators, the period ones that period's two
    meters. Never an accumulator over a declared counter, and never a period
    numerator over a lifetime denominator.
    """
    entities: list = []
    consumption = f"sensor.{denominators['consumption']}"
    production = f"sensor.{denominators['production']}" if "production" in denominators else None

    def period_source(name_suffix: str):
        return lambda cycle: f"sensor.{SYSTEM_PREFIX}_{name_suffix}_{cycle}"

    self_for = period_source("self_energy")
    consumption_for = period_source("consumption")
    production_for = period_source("production")

    # --- self-sufficiency: E_self / consumption. Always available, and the one
    # the per-device comparison uses as its baseline. ---
    entities.append(
        EnergyRatioSensor(
            hass, slug=f"{BASELINE_SLUG}_lifetime",
            numerator=f"sensor.{self_lifetime}", denominator=consumption,
            icon=ICON_SUFFICIENCY,
        )
    )
    entities += build_scored_periods(
        hass, device, name_suffix="self_sufficiency_percentage",
        unit="%", display_precision=DEFAULT_PERCENTAGE_PRECISION,
        factory=lambda cycle, slug: EnergyRatioSensor(
            hass, slug=slug, numerator=self_for(cycle),
            denominator=consumption_for(cycle), icon=ICON_SUFFICIENCY, visible=False,
        ),
    )

    if not production:
        return entities

    # --- self-consumption: E_self / production. ---
    entities.append(
        EnergyRatioSensor(
            hass, slug=f"{SYSTEM_PREFIX}_self_consumption_percentage_lifetime",
            numerator=f"sensor.{self_lifetime}", denominator=production,
            icon=ICON_CONSUMPTION,
        )
    )
    entities += build_scored_periods(
        hass, device, name_suffix="self_consumption_percentage",
        unit="%", display_precision=DEFAULT_PERCENTAGE_PRECISION,
        factory=lambda cycle, slug: EnergyRatioSensor(
            hass, slug=slug, numerator=self_for(cycle),
            denominator=production_for(cycle), icon=ICON_CONSUMPTION, visible=False,
        ),
    )

    # --- prosumption: E_self / min(consumption, production). ---
    entities.append(
        MinDenominatorRatioSensor(
            hass, slug=f"{SYSTEM_PREFIX}_prosumption_percentage_lifetime",
            numerator=f"sensor.{self_lifetime}", denominator=consumption,
            alternate=production, icon=ICON_PROSUMPTION,
        )
    )
    entities += build_scored_periods(
        hass, device, name_suffix="prosumption_percentage",
        unit="%", display_precision=DEFAULT_PERCENTAGE_PRECISION,
        factory=lambda cycle, slug: MinDenominatorRatioSensor(
            hass, slug=slug, numerator=self_for(cycle),
            denominator=consumption_for(cycle), alternate=production_for(cycle),
            icon=ICON_PROSUMPTION, visible=False,
        ),
    )
    return entities
