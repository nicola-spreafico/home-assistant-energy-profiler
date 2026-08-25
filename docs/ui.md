# The UI surface

[← Back to README](../README.md)

The integration is configured in YAML, but it is **visible** in the UI: it appears under *Settings → Devices & Services*, with one device per profiled appliance plus four global devices.

Nothing there is editable. The YAML block stays the single source of truth; the integration entry exists so Home Assistant will let it register devices, which it refuses to do for integrations that have no config entry. That is the only reason it is not a plain YAML integration anymore — opening it offers no options, and the entry itself stores nothing.

## The devices

| Device | What it holds |
| --- | --- |
| **Energy Profiler (system)** | Configuration, flows, shared counters, balance and ranking |
| **Energy Profiler (self-sufficiency)** | Only the global self-sufficiency percentage family |
| **Energy Profiler (self-consumption)** | Only the global self-consumption percentage family |
| **Energy Profiler (prosumption)** | Only the global prosumption percentage family |
| One per configured appliance | Every entity of that appliance — power, the three energy groups, cycles, and all their period meters |

The three score devices and each appliance hang off the system device (`via_device`). Entity IDs, unique IDs and histories are unchanged by this presentation split.

## Energy Profiler (system)

`sensor.energy_profiler_configuration` is its diagnostic entity. Its state is the number of profiled devices; its attributes carry the declared price, periods and flows, which self channels were resolved, and whether solar is derived. The system also retains all other global flow and Level 8 entities listed below.

For the full picture — including each device's *resolved* config after the defaults are merged, and the live state of every flow sensor — use **Download diagnostics** on the integration page. That is the fastest way to answer "is this device actually using the flows I think it is?".

### Live house shares

Instantaneous, read straight from the flows. Convenient next to the per-device figures on a dashboard, and none of them needs a template.

| Entity | Unit | Built when |
| --- | --- | --- |
| `sensor.energy_profiler_from_self_percentage` | % | flows configured |
| `sensor.energy_profiler_from_grid_percentage` | % | flows configured |
| `sensor.energy_profiler_from_solar_percentage` | % | both channels exist |
| `sensor.energy_profiler_from_battery_percentage` | % | both channels exist |

With a single channel its share equals self-sufficiency, so it is not created twice.

> **These are not the per-device percentages over the same period.** The house ones are instantaneous readings of the flows; the per-device ones divide two accumulators, so a closed period meter gives the *energy-weighted* share. On a sunny afternoon followed by a grid-fed evening the two will differ, and both are right — they answer different questions. See [Level 3](levels/03-self-sufficiency.md#percentages-are-outputs-never-inputs).


### House energy, balance and ranking

Built from `energy_flows:` ([Level 8](levels/08-prosumption.md)) rather than from the power flows, and unlike everything above they are **per period, not instantaneous** — each divides two energy counters of the same window.

| Entity | Unit | Built when |
| --- | --- | --- |
| `sensor.energy_profiler_self_energy_lifetime` (+ `_<period>`) | kWh | `energy_flows` |
| `sensor.energy_profiler_consumption_lifetime` (+ `_<period>`) | kWh | `energy_flows` |
| `sensor.energy_profiler_production_lifetime` (+ `_<period>`) | kWh | + `production` |
| `sensor.energy_profiler_energy_balance` | kWh | all four counters |
| `sensor.energy_profiler_self_ranking_<period>` | — | `energy_flows` |

Self-sufficiency and self-consumption divide the *same* self-consumed energy by two different denominators, and each is capped by the other side: in winter no behaviour pushes self-sufficiency past `production/consumption`, and in summer the same holds for self-consumption in reverse. Prosumption divides by whichever side was scarce, so it reads as a score of how well the two met **in time** rather than of how the plant is sized.

`sensor.energy_profiler_energy_balance` is the one to glance at first on a new setup: it compares the two independent readings of the self-consumed energy and should sit at noise around zero. A drift that grows means one of the four counters is measuring something else.

The ranking entity's state is the leading device; its attributes hold the ordered table plus `unprofiled_advantage_kwh` — what everything you have *not* profiled did, which is exact because the score is zero-sum across the house.

## The three score devices

Each device contains exactly one global percentage family, including its lifetime entity, period meters and hidden `…_<period>_live` helpers:

| Device | Entity family | Built when |
| --- | --- | --- |
| **Energy Profiler (self-sufficiency)** | `sensor.energy_profiler_self_sufficiency_percentage_*` | `energy_flows` |
| **Energy Profiler (self-consumption)** | `sensor.energy_profiler_self_consumption_percentage_*` | + `production` |
| **Energy Profiler (prosumption)** | `sensor.energy_profiler_prosumption_percentage_*` | + `production` |

Entity IDs, unique IDs and histories are unchanged; only their device association differs.


## Why the period meters are on the device pages

Roughly half of a device's entities are Lean meters (`_daily`, `_monthly`, `_yearly`) — the ones you actually chart. Home Assistant attaches an entity to a device only when the entity's platform is backed by a config entry, and [Lean Utility Meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter)'s platform is discovery-based with no entry of its own.

So Energy Profiler builds those meters on **its own** platform, using Lean's public `meter_from_spec`. They are still genuine Lean entities with all the Lean behaviour.

Lean's **repairs** cover these meters because the checks are scheduled by the entity itself, not by the platform. A meter that is not excluded from the recorder — or whose series has accumulated more long-term points than its cycle allows — raises the corresponding issue:

- The issue is filed under **Lean Utility Meter** in the Repairs list, not under Energy Profiler. It is a Lean meter with a Lean diagnostic, so that is where it belongs; the issue text names the entity.
- The "points overage" repair offers to run `thin_history`; the fix resolves the entity's owning platform and reaches these meters. Lean ≥ 1.2.0 is required.

Home Assistant registers entity services under the owning **platform's** domain, so the maintenance calls that reach these meters are:

| Call this | Not this |
| --- | --- |
| `energy_profiler.thin_history` | ~~`lean_utility_meter.thin_history`~~ |
| `energy_profiler.import_history` | ~~`lean_utility_meter.import_history`~~ |
| `energy_profiler.calibrate` | ~~`lean_utility_meter.calibrate`~~ |
| `energy_profiler.clear_history` | ~~`lean_utility_meter.clear_history`~~ |

Same behaviour, same parameters — the Lean implementations are re-registered verbatim. The `lean_utility_meter.*` services still exist and still serve meters you declared in Lean's own YAML; they simply no longer match these entities.

## What is still YAML-only

Adding, editing or removing devices means editing the YAML and restarting Home Assistant. There is no options flow and no reload service yet.
