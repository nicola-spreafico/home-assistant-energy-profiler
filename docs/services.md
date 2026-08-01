# Services & Actions

[← Back to README](../README.md)

The integration registers **one** service of its own, `energy_profiler.reset`, scoped to the entities it owns directly. Everything meter-shaped is a native [Lean Utility Meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter) entity and is maintained with Lean's own services — see [the second section](#maintaining-the-period-meters-lean-native-services).

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
- `sensor.<base>_self_sufficiency_<period>`

plus, from the cycles family:

- `sensor.<p>_cycles_count_<period>`
- `sensor.<p>_cycles_duration_<period>`

is a **native Lean Utility Meter entity** (created through the `lean_utility_meter` platform via discovery), so Lean's services target it directly:

| Service | Use it to |
| --- | --- |
| `lean_utility_meter.thin_history` | retro-clean a series polluted by recorder rows (see [Recorder Setup](recorder.md#what-happens-if-you-get-it-wrong)) |
| `lean_utility_meter.calibrate` | set the meter's live value manually |
| `lean_utility_meter.import_history` | import consolidated history from another entity (migrations) |
| `lean_utility_meter.clear_history` | permanently delete the meter's statistics |

Semantics, warnings and examples are documented in the [Lean services page](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter/blob/master/docs/services.md) — including the mandatory backup advice before the destructive ones. Lean's Repairs self-diagnostics (recorder exclusion, points overage) also cover these meters automatically.
