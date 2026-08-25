"""Constants for the Energy Profiler integration."""

DOMAIN = "energy_profiler"

# Top-level config keys
CONF_DEFAULTS = "defaults"
CONF_DEVICES = "devices"

# Shared defaults (were the generator's "globals")
CONF_ENERGY_PRICE = "energy_price"                     # energyPriceEntityId
CONF_BATTERY_AVAILABLE_ENERGY = "battery_available_energy"  # usable energy now (kWh)
# The house power flows the per-device attribution is derived from. These are
# *base* readings in W, the ones an inverter/meter integration already exposes —
# the integration computes the shares itself, so no template is asked of the user.
CONF_POWER_FLOWS = "power_flows"
CONF_FLOW_LOAD = "load"                                # total house load (the denominator)
CONF_FLOW_GRID = "grid"                                # load covered by grid import
CONF_FLOW_SOLAR = "solar"                              # load covered directly by the panels
CONF_FLOW_BATTERY = "battery"                          # load covered by battery discharge

# The channels the self share can be made of, in the order they are presented.
FLOW_CHANNELS = (CONF_FLOW_SOLAR, CONF_FLOW_BATTERY)

# The house energy meters, in kWh. Where `power_flows` describes the *load side*
# instant by instant (and can therefore be attributed per device), these are the
# whole-house counters — including the two, production and export, that have no
# per-device counterpart and never will. See energy_flows.py.
CONF_ENERGY_FLOWS = "energy_flows"
CONF_EFLOW_CONSUMPTION = "consumption"                 # total house consumption (kWh)
CONF_EFLOW_IMPORT = "import"                           # drawn from the grid (kWh)
CONF_EFLOW_PRODUCTION = "production"                   # raw output of the panels (kWh)
CONF_EFLOW_EXPORT = "export"                           # fed into the grid (kWh)

# The integration root every profiled appliance hangs off (via_device). Three
# child devices isolate the global house score families without changing any
# entity id or unique id.
SYSTEM_DEVICE_ID = "system"
SYSTEM_DEVICE_NAME = "Energy Profiler (system)"
SELF_SUFFICIENCY_DEVICE_ID = "house_energy"  # preserve the existing registry device
SELF_SUFFICIENCY_DEVICE_NAME = "Energy Profiler (self-sufficiency)"
SELF_CONSUMPTION_DEVICE_ID = "self_consumption"
SELF_CONSUMPTION_DEVICE_NAME = "Energy Profiler (self-consumption)"
PROSUMPTION_DEVICE_ID = "prosumption"
PROSUMPTION_DEVICE_NAME = "Energy Profiler (prosumption)"
SYSTEM_PREFIX = "energy_profiler"
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
CONF_INCLUDE_IN_RANKING = "include_in_ranking"           # exclude aggregate/overlapping meters
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
# The index is a multiplier around 1.0, where the second decimal is the
# difference between "did nothing" and "did slightly better than the house".
DEFAULT_INDEX_PRECISION = 2

# Feature families. The energy groups (total/running/standby) share one stack
# builder (families/energy_stack.py); cost and the grid/solar/battery split are
# sub-blocks of each group, driven by energy_price / power_flows.
FAMILY_POWER = "power"
FAMILY_ENERGY = "energy"
FAMILY_RUNNING = "running_energy"
FAMILY_CYCLES = "cycles"
FAMILY_STANDBY = "standby"
