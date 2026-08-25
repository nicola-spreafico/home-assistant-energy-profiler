"""Config flow for Energy Profiler — import only, never interactive.

The integration stays YAML-configured: this flow exists solely to obtain a
config entry, which Home Assistant requires before an integration may register
devices. Without one the UI can only show the "not set up via the UI" notice,
and every entity stays device-less.

So the entry carries no configuration of its own — `data` is deliberately empty
and the YAML block remains the single source of truth. Editing it and restarting
(or reloading) re-reads everything; there is nothing to keep in sync.
"""

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class EnergyProfilerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance flow whose only real step is the YAML import."""

    VERSION = 2

    async def async_step_import(self, import_data: dict | None = None):
        """Create the one entry that backs the whole YAML configuration."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Energy Profiler", data={})

    async def async_step_user(self, user_input: dict | None = None):
        """Refuse interactive setup: there is nothing to configure here."""
        return self.async_abort(reason="yaml_only")
