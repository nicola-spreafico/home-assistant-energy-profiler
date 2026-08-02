"""Downloadable diagnostics for the config entry.

Answers "what is this actually configured with?" from the integration page,
without opening the YAML — including the parts the YAML does not spell out: the
resolved per-device config after the defaults are merged, and which self
channels each device ended up with.

Entity ids are configuration, not secrets, and are kept as-is: redacting them
would defeat the purpose, since a wrong entity id is the most common cause of a
split that looks plausible but is wrong.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_POWER_FLOWS, DOMAIN
from .flows import resolve_flows


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the resolved configuration and the live flow readings."""
    store = hass.data.get(DOMAIN, {})
    defaults = store.get("defaults", {})
    devices = store.get("devices", [])

    def _flow_state(entity_id: str | None) -> Any:
        if not entity_id:
            return None
        state = hass.states.get(entity_id)
        return {"entity_id": entity_id, "state": state.state if state else "missing"}

    flows = defaults.get(CONF_POWER_FLOWS) or {}
    resolved_defaults = resolve_flows(defaults)

    return {
        "defaults": dict(defaults),
        "power_flows": {
            "declared": dict(flows),
            "live": {key: _flow_state(eid) for key, eid in flows.items()},
            "channels": resolved_defaults["channels"] if resolved_defaults else [],
            "solar_is_derived": bool(resolved_defaults and resolved_defaults["derives_solar"]),
        },
        "devices": [
            {
                "prefix": device["prefix"],
                "families": device.get("families", []),
                "periods": device.get("periods"),
                "channels": (
                    channels["channels"] if (channels := resolve_flows(device)) else []
                ),
                # The merged view: what this device actually runs with, defaults included.
                "resolved": {
                    key: value
                    for key, value in device.items()
                    if key not in ("families", "prefix")
                },
            }
            for device in devices
        ],
    }
