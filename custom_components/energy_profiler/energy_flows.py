"""House energy counters: the generation side, which no device can be given.

``power_flows`` (see flows.py) describes the *load side* instant by instant, and
that is what makes per-device attribution possible: an appliance has its own
energy meter, so a measured quantity exists to apportion using the house ratios.

This module covers what has no per-device counterpart. Production and export are
whole-house facts, and — importantly — not merely *hard* to split per device but
**degenerate** if you try. The only defensible way to hand a device a slice of
the production is in proportion to the self-production it absorbed::

    P_d = P × (self_d / E_self)   ⟹   self_d / P_d = E_self / P

``self_d`` cancels: every appliance would score exactly the house figure. So a
per-device self-consumption is not an approximation worth making, it is a number
with no information in it at all. The generation side lives here, once.

**What is declared, and why those four.** Four counters, of which two are
required. The house obeys one identity::

    consumption = production + import − export

so the self-consumed energy has two equivalent readings::

    E_self = consumption − import = production − export

``consumption`` and ``import`` are required because their difference *is*
``E_self`` and their ratio *is* the baseline that per-device scoring needs.
``production`` unlocks the two scores measured against the generation side.
``export`` earns nothing new — ``E_self`` is already known — so it is kept only
as the cross-check: when all four are declared, the two readings above must
agree, and their disagreement is published as a diagnostic.

**Why counters and not power.** Everything here is meant to be *persisted per
period*, and a period figure has to be a ratio of two energies. Averaging an
instantaneous percentage over a day measures something else entirely: the gap
between the two is ``cov(power, self-share) / mean(power)`` — that is, exactly
the tendency to run loads while the sun is up, which is the whole quantity of
interest. Integrating power here ourselves would be a second-rate way to reach
counters the inverter already publishes.
"""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_EFLOW_CONSUMPTION,
    CONF_EFLOW_EXPORT,
    CONF_EFLOW_IMPORT,
    CONF_EFLOW_PRODUCTION,
    CONF_ENERGY_FLOWS,
)


def resolve_energy_flows(defaults: dict[str, Any]) -> dict[str, Any] | None:
    """Return the resolved house energy config, or None when not declared.

    ``has_generation`` gates the scores that divide by production;
    ``has_balance`` gates the cross-check that needs all four counters.
    """
    flows = defaults.get(CONF_ENERGY_FLOWS)
    if not flows:
        return None

    production = flows.get(CONF_EFLOW_PRODUCTION)
    export = flows.get(CONF_EFLOW_EXPORT)

    return {
        CONF_EFLOW_CONSUMPTION: flows[CONF_EFLOW_CONSUMPTION],
        CONF_EFLOW_IMPORT: flows[CONF_EFLOW_IMPORT],
        CONF_EFLOW_PRODUCTION: production,
        CONF_EFLOW_EXPORT: export,
        "has_generation": bool(production),
        "has_balance": bool(production and export),
    }
