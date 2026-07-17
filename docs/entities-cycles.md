# Entities: cycle tracking — per-run analytics

[← Back to the entity catalog](entities.md) · [README](../README.md)

What `cycle_tracking:` adds on top of the [`running:` signal](entities-running.md): boundaries, validation, per-run metrics with means and totals, and the bus events. `<p>` is the device prefix; `<period>` one entity per configured period. Markers (🚫/💤/📈/↺) are defined in the [catalog overview](entities.md).

## Cycle boundary and engine

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_cycle_start_snapshot` 💤 | timestamp | When the current/last cycle opened; attributes hold each metric's baseline (`initial_energy`, `initial_cost`, …) |
| `sensor.<p>_cycle_stop_snapshot` 💤 | timestamp | When the last cycle closed; attributes hold the final values (`final_energy`, …) |
| `sensor.<p>_cycle_validation_status` 📈 | — | Verdict on the last closed cycle: `valid`, `too_short`, `too_long`, `too_little_energy`, `too_much_energy` (see [limits](configuration.md#cycle-analytics-cycle_tracking)) |
| `sensor.<p>_cycles_count_lifetime` 💤 ↺ | cycles | Number of valid completed cycles — also the engine that drives every cycle sensor on this page |
| `sensor.<p>_cycles_count_<period>` 🚫 | cycles | Lean period meters: how many runs per period |

## Per-metric analytics

Each available metric gets the same four views:

- **Completed** 📈 — the value for the **last completed cycle**; its state history is the per-run log
- **Live** 💤 — the **in-progress** cycle's value so far (0 when idle)
- **Lifetime** 💤 ↺ — total accumulated over all *valid* cycles (a discarded run counts in the energy groups but not here)
- **Mean** 📈 — average per valid cycle (`lifetime / count`)

Which metrics exist depends on the configured sources; explicit ids (note the two irregular live ids for savings/grid-cost):

| Metric | Requires | Unit | Completed | Live | Lifetime | Mean |
| --- | --- | --- | --- | --- | --- | --- |
| energy | — | kWh | `…_cycle_completed_energy` | `…_cycle_live_energy` | `…_cycles_energy_lifetime` | `…_cycles_energy_mean` |
| cost | price | € | `…_cycle_completed_cost` | `…_cycle_live_cost` | `…_cycles_cost_lifetime` | `…_cycles_cost_mean` |
| from self | ss | kWh | `…_cycle_completed_energy_from_self` | `…_cycle_live_energy_from_self` | `…_cycles_energy_from_self_lifetime` | `…_cycles_energy_from_self_mean` |
| from grid | ss | kWh | `…_cycle_completed_energy_from_grid` | `…_cycle_live_energy_from_grid` | `…_cycles_energy_from_grid_lifetime` | `…_cycles_energy_from_grid_mean` |
| from solar | ss + share | kWh | `…_cycle_completed_energy_from_solar` | `…_cycle_live_energy_from_solar` | `…_cycles_energy_from_solar_lifetime` | `…_cycles_energy_from_solar_mean` |
| from battery | ss + share | kWh | `…_cycle_completed_energy_from_battery` | `…_cycle_live_energy_from_battery` | `…_cycles_energy_from_battery_lifetime` | `…_cycles_energy_from_battery_mean` |
| savings | price + ss | € | `…_cycle_completed_energy_from_grid_savings` | `…_cycle_live_savings_from_grid` | `…_cycles_energy_from_grid_savings_lifetime` | `…_cycles_energy_from_grid_savings_mean` |
| grid cost | price + ss | € | `…_cycle_completed_energy_from_grid_cost` | `…_cycle_live_cost_from_grid` | `…_cycles_energy_from_grid_cost_lifetime` | `…_cycles_energy_from_grid_cost_mean` |

(`price` = `energy_price`, `ss` = `self_sufficiency_source`, `share` = `solar_share_source`/`battery_share_source`; `…` = `sensor.<p>`.)

## Duration and derived

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_cycles_duration_lifetime` 💤 ↺ | s | Total running time over all valid cycles |
| `sensor.<p>_cycles_duration_<period>` 🚫 | s | Lean period meters: running time per period |
| `sensor.<p>_cycle_completed_duration` 📈 | s | Duration of the last completed cycle |
| `sensor.<p>_cycle_live_duration` 💤 | s | Elapsed time of the in-progress cycle (ticks while running) |
| `sensor.<p>_cycles_duration_mean` 📈 | s | Average cycle duration |
| `sensor.<p>_cycles_duration_summary_human` 💤 | — | Total running time formatted for dashboards (`12h 36m`) |
| `sensor.<p>_cycle_completed_self_sufficiency` 📈 | % | Self-sufficiency of the last completed cycle (with `self_sufficiency_source`) |
| `sensor.<p>_cycle_live_self_sufficiency` 💤 | % | Self-sufficiency of the in-progress cycle |
| `sensor.<p>_cycles_self_sufficiency_percentage_mean` 📈 | % | Energy-weighted self-sufficiency across all valid cycles |
| `sensor.<p>_cycle_completed_costovertime` 📈 | €/h | Cost per hour of the last completed cycle (with `energy_price`) |
| `sensor.<p>_cycles_costovertime_mean` 📈 | €/h | Average cost per running hour across all valid cycles |

## Events

When a cycle closes, one of two events fires on the Home Assistant bus — the intended hook for notifications and automations (this replaces the legacy generator's built-in notify):

- `energy_insights_monitor_cycle_completed` — the cycle passed the configured limits
- `energy_insights_monitor_cycle_discarded` — it failed them (counters and means were not touched)

Payload:

```yaml
device: washing_machine_em   # the device prefix
energy_kwh: 1.05             # energy delta of the cycle
duration_s: 5411.2           # duration in seconds
status: valid                # or too_short / too_long / too_little_energy / too_much_energy
cycle_count: 42              # valid cycles so far
```

## Inventory

Fully-configured, with `[daily, monthly, yearly]`: **52 entities** (46 fixed + 2 per period): the 4 boundary/engine sensors, `cycles_count_<period>` and `cycles_duration_<period>` meters, the 8×4 metric matrix, and the 10 duration/derived sensors.
