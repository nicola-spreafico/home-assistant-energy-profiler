"""Voluptuous config schema for the Energy Profiler integration.

Mirrors the shape of the old generator's ``config.jsonc`` (globals + devices),
but validated at load time so typos surface as clear errors instead of silently
broken Jinja.

The device model separates *signals* from *consumers*:
- ``running:`` — a signal: defines the running detection and creates
  ``binary_sensor.<prefix>_running``, nothing else;
- ``cycle_tracking:`` — a consumer: run-cycle analytics over the running signal
  (owns its ``limits``); requires ``running:``;
- ``standby:`` — signal + consumer: the standby gatekeeper (default flavor =
  "not running", or a custom power/template condition) and the standby energy
  family gated on it.
"""

import voluptuous as vol

from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_DEFAULTS,
    CONF_DEVICES,
    CONF_ENERGY_PRICE,
    CONF_POWER_FLOWS,
    CONF_FLOW_LOAD,
    CONF_FLOW_GRID,
    CONF_FLOW_SOLAR,
    CONF_FLOW_BATTERY,
    FLOW_CHANNELS,
    CONF_ENERGY_FLOWS,
    CONF_EFLOW_CONSUMPTION,
    CONF_EFLOW_IMPORT,
    CONF_EFLOW_PRODUCTION,
    CONF_EFLOW_EXPORT,
    CONF_NAME_SUFFIX,
    CONF_LIVE_UPDATE_INTERVAL,
    CONF_PERIODS,
    CONF_INSTANT_PERIODS,
    CONF_COST_PRECISION,
    CONF_NAME,
    CONF_POWER,
    CONF_ENERGY,
    CONF_RUNNING,
    CONF_CYCLE_TRACKING,
    CONF_LIMITS,
    CONF_STANDBY,
    CONF_TRIGGER,
    CONF_ON_ABOVE,
    CONF_ON_DELAY,
    CONF_OFF_BELOW,
    CONF_OFF_DELAY,
    CONF_ON_BELOW,
    CONF_OFF_ABOVE,
    CONF_AVAILABLE,
    CONF_STATE,
    DEFAULT_NAME_SUFFIX,
    DEFAULT_PERIODS,
    DEFAULT_COST_PRECISION,
)

PERIOD = vol.In(["hourly", "daily", "weekly", "monthly", "bimonthly", "quarterly", "yearly"])


def _validate_power_flows(value: dict) -> dict:
    """Reject the two ways a flow block can be meaningless or ambiguous.

    `load` exists to derive the solar contribution, which is the one reading
    people rarely have natively. Giving both is over-specified: rather than
    silently picking one, say so — a wrong choice here skews every split
    downstream with no visible symptom.
    """
    if CONF_FLOW_LOAD in value and CONF_FLOW_SOLAR in value:
        raise vol.Invalid(
            f"'{CONF_POWER_FLOWS}' declares both '{CONF_FLOW_LOAD}' and "
            f"'{CONF_FLOW_SOLAR}': '{CONF_FLOW_LOAD}' is only used to derive the "
            f"solar contribution, so it is redundant here. Drop one of the two."
        )
    if CONF_FLOW_LOAD not in value and not any(c in value for c in FLOW_CHANNELS):
        raise vol.Invalid(
            f"'{CONF_POWER_FLOWS}' needs '{CONF_FLOW_LOAD}' or at least one of "
            f"'{CONF_FLOW_SOLAR}' / '{CONF_FLOW_BATTERY}': with '{CONF_FLOW_GRID}' "
            f"alone every device would be 100% grid-fed."
        )
    return value


# power_flows: — the house flows, in W, that per-device attribution derives from.
# `grid` is always required (it is the portion that always exists); `load` and
# the channels shape what the split can say. See flows.py for the resolution.
POWER_FLOWS_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(CONF_FLOW_LOAD): cv.entity_id,
            vol.Required(CONF_FLOW_GRID): cv.entity_id,
            vol.Optional(CONF_FLOW_SOLAR): cv.entity_id,
            vol.Optional(CONF_FLOW_BATTERY): cv.entity_id,
        }
    ),
    _validate_power_flows,
)

# energy_flows: — the house kWh counters. Deliberately a separate block from
# `power_flows` rather than more keys inside it: every `power_flows` key is a
# *contribution to the house load* and they sum to it, an invariant the schema
# already defends above. Production and export are not contributions to the
# load, and folding them in would quietly dissolve that meaning.
#
# `consumption` + `import` are required because everything else is built on
# them: their difference is the self-consumed energy, and their ratio is the
# house baseline every per-device comparison is scored against. `production`
# unlocks the two scores that look at the generation side; `export` adds only
# the cross-check, since the self-consumed energy is already known without it.
ENERGY_FLOWS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EFLOW_CONSUMPTION): cv.entity_id,
        vol.Required(CONF_EFLOW_IMPORT): cv.entity_id,
        vol.Optional(CONF_EFLOW_PRODUCTION): cv.entity_id,
        vol.Optional(CONF_EFLOW_EXPORT): cv.entity_id,
    }
)

# running: — the detection signal. Two trigger flavors: power threshold or template.
RUNNING_SCHEMA = vol.Any(
    vol.Schema(
        {
            vol.Required(CONF_TRIGGER): "power",
            vol.Optional(CONF_ON_ABOVE, default=0): vol.Coerce(float),
            vol.Optional(CONF_OFF_BELOW, default=1): vol.Coerce(float),
            vol.Optional(CONF_ON_DELAY, default="00:00:00"): cv.time_period,
            vol.Optional(CONF_OFF_DELAY, default="00:00:00"): cv.time_period,
        }
    ),
    vol.Schema(
        {
            vol.Required(CONF_TRIGGER): "template",
            vol.Required(CONF_AVAILABLE): cv.template,
            vol.Required(CONF_STATE): cv.template,
        }
    ),
)

# standby: — boolean or a custom condition. `true` keeps the default gating
# (standby == running off, needs `running:`); a trigger block defines an
# independent standby condition. The power flavor has inverted threshold
# semantics: standby starts when power *drops below* `on_below` (for
# `on_delay`) and ends when it *rises above* `off_above` (default: same as
# on_below) for `off_delay`.
STANDBY_SCHEMA = vol.Any(
    cv.boolean,
    vol.Schema(
        {
            vol.Required(CONF_TRIGGER): "power",
            vol.Required(CONF_ON_BELOW): vol.Coerce(float),
            vol.Optional(CONF_OFF_ABOVE): vol.Coerce(float),
            vol.Optional(CONF_ON_DELAY, default="00:00:00"): cv.time_period,
            vol.Optional(CONF_OFF_DELAY, default="00:00:00"): cv.time_period,
        }
    ),
    vol.Schema(
        {
            vol.Required(CONF_TRIGGER): "template",
            vol.Required(CONF_AVAILABLE): cv.template,
            vol.Required(CONF_STATE): cv.template,
        }
    ),
)

LIMITS_SCHEMA = vol.Schema(
    {
        vol.Optional("min_duration"): cv.time_period,
        vol.Optional("max_duration"): cv.time_period,
        vol.Optional("min_energy"): vol.Coerce(float),
        vol.Optional("max_energy"): vol.Coerce(float),
    }
)


def _normalize_cycle_tracking(value):
    """Allow `cycle_tracking: true` as shorthand for an empty options block."""
    if value is True:
        return {}
    if value is False:
        return None
    return value


# cycle_tracking: — run-cycle analytics over the running signal. `true` is a
# shorthand for "enabled with no limits".
CYCLE_TRACKING_SCHEMA = vol.All(
    vol.Any(
        cv.boolean,
        vol.Schema({vol.Optional(CONF_LIMITS): LIMITS_SCHEMA}),
    ),
    _normalize_cycle_tracking,
)

DEFAULTS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENERGY_PRICE): cv.entity_id,
        vol.Optional(CONF_POWER_FLOWS): POWER_FLOWS_SCHEMA,
        # Defaults only, with no per-device counterpart: these are readings of
        # the whole house, and a device overriding them would be claiming a
        # second house rather than a different view of this one.
        vol.Optional(CONF_ENERGY_FLOWS): ENERGY_FLOWS_SCHEMA,
        vol.Optional(CONF_NAME_SUFFIX, default=DEFAULT_NAME_SUFFIX): cv.string,
        vol.Optional(CONF_LIVE_UPDATE_INTERVAL): cv.time_period,
        vol.Optional(CONF_PERIODS, default=DEFAULT_PERIODS): vol.All(cv.ensure_list, [PERIOD]),
        # No default on purpose: absent means "follow periods". An explicit list
        # (including the empty one, which switches them off) overrides that.
        vol.Optional(CONF_INSTANT_PERIODS): vol.All(cv.ensure_list, [PERIOD]),
        # Decimals shown by the € entities. Display only — see DEFAULT_COST_PRECISION.
        vol.Optional(CONF_COST_PRECISION, default=DEFAULT_COST_PRECISION): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=10)
        ),
    }
)

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.slug,
        vol.Required(CONF_POWER): cv.entity_id,
        vol.Required(CONF_ENERGY): cv.entity_id,
        # Per-device overrides of the shared defaults. `null` explicitly opts the
        # device out of the corresponding family even when a default is set.
        vol.Optional(CONF_ENERGY_PRICE): vol.Any(None, cv.entity_id),
        # Replaced wholesale, never merged key-by-key: a half-inherited flow block
        # would mix two houses' readings. `null` opts the device out of the split.
        vol.Optional(CONF_POWER_FLOWS): vol.Any(None, POWER_FLOWS_SCHEMA),
        vol.Optional(CONF_LIVE_UPDATE_INTERVAL): cv.time_period,
        vol.Optional(CONF_PERIODS): vol.All(cv.ensure_list, [PERIOD]),
        vol.Optional(CONF_INSTANT_PERIODS): vol.All(cv.ensure_list, [PERIOD]),
        vol.Optional(CONF_COST_PRECISION): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=10)
        ),
        # Signals and their consumers.
        vol.Optional(CONF_RUNNING): RUNNING_SCHEMA,
        vol.Optional(CONF_CYCLE_TRACKING): CYCLE_TRACKING_SCHEMA,
        vol.Optional(CONF_STANDBY, default=False): STANDBY_SCHEMA,
    }
)

# The domain is a single dict: ONE global `defaults` block plus a `devices` list.
# Splitting across package files works natively via HA's package merge: put
# `defaults:` in exactly one file (it is the single global default for the whole
# system) and spread `devices:` across as many files as you like — HA concatenates
# the device lists into one and validates the merged whole (so a defaults-only file
# and devices-only files are each fine on their own).
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_DEFAULTS, default={}): DEFAULTS_SCHEMA,
                vol.Required(CONF_DEVICES): vol.All(cv.ensure_list, [DEVICE_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)
