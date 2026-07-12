"""Voluptuous config schema for the Energy Monitor integration.

Mirrors the shape of the old generator's ``config.jsonc`` (globals + devices),
but validated at load time so typos surface as clear errors instead of silently
broken Jinja.
"""

import voluptuous as vol

from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_DEFAULTS,
    CONF_DEVICES,
    CONF_ENERGY_PRICE,
    CONF_SELF_SUFFICIENCY_SOURCE,
    CONF_NAME_SUFFIX,
    CONF_LIVE_UPDATE_INTERVAL,
    CONF_CYCLES,
    CONF_NAME,
    CONF_POWER,
    CONF_ENERGY,
    CONF_SWITCH,
    CONF_RUN,
    CONF_LIMITS,
    CONF_STANDBY,
    CONF_NOTIFY_ON_COMPLETE,
    CONF_TRIGGER,
    CONF_ON_ABOVE,
    CONF_ON_DELAY,
    CONF_OFF_BELOW,
    CONF_OFF_DELAY,
    CONF_AVAILABLE,
    CONF_STATE,
    DEFAULT_NAME_SUFFIX,
    DEFAULT_CYCLES,
)

CYCLE = vol.In(["hourly", "daily", "weekly", "monthly", "bimonthly", "quarterly", "yearly"])

# run: — presence enables cycle tracking. Two trigger flavors: power threshold or template.
RUN_SCHEMA = vol.Any(
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

LIMITS_SCHEMA = vol.Schema(
    {
        vol.Optional("min_duration"): cv.time_period,
        vol.Optional("max_duration"): cv.time_period,
        vol.Optional("min_energy"): vol.Coerce(float),
        vol.Optional("max_energy"): vol.Coerce(float),
    }
)

DEFAULTS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENERGY_PRICE): cv.entity_id,
        vol.Optional(CONF_SELF_SUFFICIENCY_SOURCE): cv.entity_id,
        vol.Optional(CONF_NAME_SUFFIX, default=DEFAULT_NAME_SUFFIX): cv.string,
        vol.Optional(CONF_LIVE_UPDATE_INTERVAL): cv.time_period,
        vol.Optional(CONF_CYCLES, default=DEFAULT_CYCLES): vol.All(cv.ensure_list, [CYCLE]),
    }
)

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.slug,
        vol.Required(CONF_POWER): cv.entity_id,
        vol.Required(CONF_ENERGY): cv.entity_id,
        vol.Optional(CONF_SWITCH): cv.entity_id,
        # Per-device overrides of the shared defaults
        vol.Optional(CONF_ENERGY_PRICE): cv.entity_id,
        vol.Optional(CONF_SELF_SUFFICIENCY_SOURCE): cv.entity_id,
        vol.Optional(CONF_LIVE_UPDATE_INTERVAL): cv.time_period,
        vol.Optional(CONF_CYCLES): vol.All(cv.ensure_list, [CYCLE]),
        # Cycle tracking (optional): presence of `run` turns it on
        vol.Optional(CONF_RUN): RUN_SCHEMA,
        vol.Optional(CONF_LIMITS): LIMITS_SCHEMA,
        vol.Optional(CONF_STANDBY, default=False): cv.boolean,
        vol.Optional(CONF_NOTIFY_ON_COMPLETE, default=False): cv.boolean,
    }
)

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
