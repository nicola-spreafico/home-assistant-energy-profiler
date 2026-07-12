"""Constants for the Energy Insights Monitor integration."""

DOMAIN = "energy_insights_monitor"

# Top-level config keys
CONF_DEFAULTS = "defaults"
CONF_DEVICES = "devices"

# Shared defaults (were the generator's "globals")
CONF_ENERGY_PRICE = "energy_price"                     # energyPriceEntityId
CONF_SELF_SUFFICIENCY_SOURCE = "self_sufficiency_source"  # selfSufficiencyPercentageEntityId
CONF_NAME_SUFFIX = "name_suffix"                       # entitiesPrefixEnd (default "_em")
CONF_LIVE_UPDATE_INTERVAL = "live_update_interval"
CONF_CYCLES = "cycles"                                 # which lean cycles to create

# Per-device keys
CONF_NAME = "name"                                     # entitiesPrefix
CONF_POWER = "power"                                   # powerSensorId
CONF_ENERGY = "energy"                                 # energySensorId
CONF_SWITCH = "switch"                                 # powerSwitchId (optional)
CONF_RUN = "run"                                       # cycles.running -> presence enables cycle tracking
CONF_LIMITS = "limits"                                 # cycles.min/max duration/energy
CONF_STANDBY = "standby"                               # enable standby family
CONF_NOTIFY_ON_COMPLETE = "notify_on_complete"         # sendCycleCompletedNotification

# run.* keys
CONF_TRIGGER = "trigger"                               # "power" | "template"
CONF_ON_ABOVE = "on_above"
CONF_ON_DELAY = "on_delay"
CONF_OFF_BELOW = "off_below"
CONF_OFF_DELAY = "off_delay"
CONF_AVAILABLE = "available"                           # template trigger availability
CONF_STATE = "state"                                   # template trigger state

# Defaults
DEFAULT_NAME_SUFFIX = "_em"
DEFAULT_CYCLES = ["daily", "monthly", "yearly"]

# Feature families (mirror the generator's template folders)
FAMILY_ENERGY = "energy"
FAMILY_COST = "cost"
FAMILY_SELF_SUFFICIENCY = "self_sufficiency"
FAMILY_CYCLES = "cycles"
FAMILY_STANDBY = "standby"
