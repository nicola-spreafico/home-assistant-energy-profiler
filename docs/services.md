# Services & Actions

[← Back to README](../README.md)

The integration registers `energy_profiler.reset` for the entities it owns directly, plus the four [Lean Utility Meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter) maintenance services re-exposed under its own domain — see [the second section](#maintaining-the-period-meters-lean-native-services) for why the domain is `energy_profiler` and not `lean_utility_meter`.

## `energy_profiler.reset`

Zeroes a resettable entity. The idiomatic replacement for the legacy generator's `reset_*` scripts.

```yaml
action: energy_profiler.reset
target:
  entity_id: sensor.washing_machine_em_power_max
```

Calling it on an entity that has nothing to reset (means, live views, snapshots) is a deliberate **no-op** — you can safely target groups of entities.

**Supported (resettable) entities**, `<p>` = device prefix:

| Entity | Resetting it means |
| --- | --- |
| `sensor.<p>_power_max` | start a fresh peak-power measurement |
| `sensor.<base>_lifetime` | restart an energy group's all-time total (`<base>` = `<p>_energy`, `<p>_running_energy` or `<p>_standby_energy`) |
| `sensor.<base>_cost_lifetime` | restart a group's cost total |
| `sensor.<base>_from_self_lifetime`, `sensor.<base>_from_grid_lifetime` | restart a group's self/grid split |
| `sensor.<base>_from_solar_lifetime`, `sensor.<base>_from_battery_lifetime` | restart a group's solar/battery split |
| `sensor.<base>_from_grid_savings_lifetime`, `sensor.<base>_from_grid_cost_lifetime` | restart the monetary views of a group's split |
| `sensor.<p>_cycles_count_lifetime` | restart the valid-cycle counter (means recompute from the new base) |
| `sensor.<p>_cycles_duration_lifetime` | restart the total running time |
| `sensor.<p>_cycles_<metric>_lifetime` (energy, cost, …) | restart a per-run metric accumulator |
| `sensor.<p>_cycle_completed_*` | zero the last-completed-cycle value |

> ⚠️ **Resetting a `*_lifetime` moves the baseline downstream families read from.** The drop to zero is handled safely by the period meters (a source reset never injects a phantom delta), but ratios and means computed from that accumulator — self-sufficiency %, per-run means — restart from the new base. Reset lifetimes only when a fresh start is actually what you want.

## Maintaining the period meters (Lean native services)

Every per-period meter — the entities ending in a period suffix (`_hourly`, `_daily`, `_weekly`, `_monthly`, `_bimonthly`, `_quarterly`, `_yearly`). For each energy group `<base>` (`<p>_energy`, `<p>_running_energy`, `<p>_standby_energy`):

- `sensor.<base>_<period>`
- `sensor.<base>_cost_<period>`
- `sensor.<base>_from_self_<period>` / `sensor.<base>_from_grid_<period>`
- `sensor.<base>_from_solar_<period>` / `sensor.<base>_from_battery_<period>`
- `sensor.<base>_from_grid_savings_<period>` / `sensor.<base>_from_grid_cost_<period>`
- `sensor.<base>_from_self_percentage_<period>`
- `sensor.<base>_from_grid_percentage_<period>`, `sensor.<base>_from_solar_percentage_<period>`, `sensor.<base>_from_battery_percentage_<period>`

plus, from the cycles family:

- `sensor.<p>_cycles_count_<period>`
- `sensor.<p>_cycles_duration_<period>`

is a **native Lean Utility Meter entity**, with all of Lean's behaviour and self-diagnostics. But it is created on *this* integration's platform (the only way it can belong to a device — see [The UI surface](ui.md#why-the-period-meters-are-on-the-device-pages)), and Home Assistant registers entity services under the platform's own domain. So the maintenance calls are:

| Service | Use it to |
| --- | --- |
| `energy_profiler.thin_history` | retro-clean a series polluted by recorder rows (see [Recorder Setup](recorder.md#what-happens-if-you-get-it-wrong)) |
| `energy_profiler.calibrate` | set the meter's live value manually |
| `energy_profiler.import_history` | import consolidated history from another entity (migrations) |
| `energy_profiler.clear_history` | permanently delete the meter's statistics |

> ⚠️ **Not `lean_utility_meter.thin_history`.** Those services still exist and still serve meters you declared in Lean's own YAML, but they no longer match these entities. An automation written against the Lean domain will silently target nothing.

The implementations are Lean's, re-registered verbatim: same parameters, same semantics, same warnings — documented on the [Lean services page](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter/blob/master/docs/services.md), including the mandatory backup advice before the destructive ones. Lean's Repairs self-diagnostics (recorder exclusion, points overage) cover these meters automatically, since they are scheduled by the entity rather than by the platform.
