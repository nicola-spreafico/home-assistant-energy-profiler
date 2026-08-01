"""Constants for the Energy Profiler integration."""

DOMAIN = "energy_profiler"

# Top-level config keys
CONF_DEFAULTS = "defaults"
CONF_DEVICES = "devices"

# Shared defaults (were the generator's "globals")
CONF_ENERGY_PRICE = "energy_price"                     # energyPriceEntityId
CONF_SELF_SUFFICIENCY_SOURCE = "self_sufficiency_source"  # selfSufficiencyPercentageEntityId
# Optional second-level split of the self share into solar vs battery. The user
# provides ONE of the two (the other is the complement): a % *of the
# self-consumed energy* coming from solar, or from the battery.
CONF_SOLAR_SHARE_SOURCE = "solar_share_source"
CONF_BATTERY_SHARE_SOURCE = "battery_share_source"
CONF_NAME_SUFFIX = "name_suffix"                       # entitiesPrefixEnd (default "_em")
CONF_LIVE_UPDATE_INTERVAL = "live_update_interval"
CONF_PERIODS = "periods"                               # which lean meter periods to create
CONF_INSTANT_PERIODS = "instant_periods"               # overrides periods for the instant cost projections
CONF_COST_PRECISION = "cost_precision"                 # decimals *shown* by the € entities (display only)

# Per-device keys
CONF_NAME = "name"                                     # entitiesPrefix
CONF_POWER = "power"                                   # powerSensorId
CONF_ENERGY = "energy"                                 # energySensorId
CONF_RUNNING = "running"                               # signal: creates binary_sensor _running
CONF_CYCLE_TRACKING = "cycle_tracking"                 # consumer: run-cycle analytics (needs running)
CONF_LIMITS = "limits"                                 # cycle_tracking.limits: min/max duration/energy
CONF_STANDBY = "standby"                               # signal+consumer: standby energy tracking

# running.* / standby.* trigger keys
CONF_TRIGGER = "trigger"                               # "power" | "template"
CONF_ON_ABOVE = "on_above"
CONF_ON_DELAY = "on_delay"
CONF_OFF_BELOW = "off_below"
CONF_OFF_DELAY = "off_delay"
CONF_AVAILABLE = "available"                           # template trigger availability
CONF_STATE = "state"                                   # template trigger state
# standby power-trigger thresholds (inverted semantics vs running)
CONF_ON_BELOW = "on_below"                             # standby when power drops below
CONF_OFF_ABOVE = "off_above"                           # standby ends when power rises above

# Defaults
DEFAULT_NAME_SUFFIX = "_em"
DEFAULT_PERIODS = ["daily", "monthly", "yearly"]
# Cost accumulators integrate in Decimal and are deliberately never rounded, so
# their raw state carries ~10 decimals. This caps what the UI *shows* (cents),
# nothing else: the stored state and the statistics keep their full precision.
DEFAULT_COST_PRECISION = 2
# Percentages carry no device class, so HA has no default precision for them
# either (same gap as MONETARY) and would render the raw state. Not exposed as an
# option: a tenth of a point is enough for a self-sufficiency reading.
DEFAULT_PERCENTAGE_PRECISION = 1

# Feature families. The energy groups (total/running/standby) share one stack
# builder (families/energy_stack.py); cost and solar-split are sub-blocks of
# each group, driven by energy_price / self_sufficiency_source.
FAMILY_POWER = "power"
FAMILY_ENERGY = "energy"
FAMILY_RUNNING = "running_energy"
FAMILY_CYCLES = "cycles"
FAMILY_STANDBY = "standby"
