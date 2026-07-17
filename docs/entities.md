# Entities

[← Back to README](../README.md)

The complete catalog of what a device can expose, grouped by family. `<p>` stands for the device prefix (`<name><name_suffix>`, e.g. `washing_machine_em`); `<period>` for each configured meter period (`daily`, `monthly`, …). Which families a device gets is decided by its options — see [Configuration](configuration.md).

Each entity carries two markers:

- **Recorder class** — how to treat it in the recorder (details in [Recorder Setup](recorder.md)):
  - 🚫 *never record* — a Lean period meter that writes its own long-term statistics; recording it corrupts the series
  - 💤 *exclude* — live view or restore-based accumulator; recording is pure database bloat
  - 📈 *worth recording* — changes at meaningful moments; its state history is useful
- **↺ resettable** — supports the `energy_insights_monitor.reset` entity service (zeroes the value). The 🚫 period meters are native Lean entities instead, maintained via Lean's own services — see [Services & Actions](services.md).

## Power — always on

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_power_max` 📈 ↺ | W | Running peak of the power sensor, kept across restarts until you reset it |
| `sensor.<p>_power_from_self` 💤 | W | Instantaneous share of the current draw covered by self-production (`power × pct`). Requires `self_sufficiency_source` |
| `sensor.<p>_power_from_grid` 💤 | W | Instantaneous share imported from the grid — the exact remainder, so the two always sum to the measured power |

## Energy — always on

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_lifetime` 💤 ↺ | kWh | The device's all-time total, **decoupled from the hardware sensor**: accumulates only positive deltas, so meter resets or a plug swap never zero it or inject phantom energy. Every other family reads from this, inheriting the decoupling |
| `sensor.<p>_energy_<period>` 🚫 | kWh | Lean period meter over the lifetime: live counter in the UI, one consolidated LTS row per closed period |

## Cost — requires `energy_price`

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_cost_lifetime` 💤 ↺ | € | Cost integrator: each energy delta is priced at the tariff valid *at that moment*, so tariff changes are handled naturally |
| `sensor.<p>_energy_cost_<period>` 🚫 | € | Lean period meter over the cost integrator |
| `sensor.<p>_energy_cost_instant_hourly` 💤 | €/h | Projected cost rate if the current draw held for an hour (`power × price`) |
| `sensor.<p>_energy_cost_instant_daily` 💤 | €/d | Same projection over a day |
| `sensor.<p>_energy_cost_instant_monthly` 💤 | €/m | Same projection over a 30-day month |
| `sensor.<p>_energy_cost_instant_yearly` 💤 | €/y | Same projection over a year |

## Self-sufficiency — requires `self_sufficiency_source`

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_from_self_lifetime` 💤 ↺ | kWh | Energy covered by self-production: each lifetime delta split by the current self-sufficiency % |
| `sensor.<p>_energy_from_grid_lifetime` 💤 ↺ | kWh | Energy imported from the grid — computed as the exact remainder of the same atomic split, so `from_self + from_grid = energy_lifetime`, always |
| `sensor.<p>_energy_from_self_<period>` 🚫 | kWh | Lean period meters over the two splits |
| `sensor.<p>_energy_from_grid_<period>` 🚫 | kWh | ” |
| `sensor.<p>_energy_self_sufficiency_lifetime` 💤 | % | Live all-time ratio `from_self / total` |
| `sensor.<p>_energy_self_sufficiency_<period>` 🚫 | % | Lean **gauge** meters: the percentage is snapshotted into one LTS row per period (it can move up and down within it) |

With a price configured, two monetary views of the split are added:

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_from_grid_savings_lifetime` 💤 ↺ | € | What self-production saved you: the value of `from_self` energy priced at the purchase tariff |
| `sensor.<p>_energy_from_grid_cost_lifetime` 💤 ↺ | € | What the grid imports actually cost (`from_grid` priced) |
| `sensor.<p>_energy_from_grid_savings_<period>` 🚫 | € | Lean period meters over the two |
| `sensor.<p>_energy_from_grid_cost_<period>` 🚫 | € | ” |

## Cycles — requires `running:` and `cycle_tracking:`

### Run detection and cycle boundary

| Entity | Unit | Description |
| --- | --- | --- |
| `binary_sensor.<p>_running` 📈 | — | The gatekeeper: `on` while the appliance runs, according to the configured power threshold or template trigger. Created by `running:` alone (it is the signal); cycle open/close and default-flavor standby gating follow it |
| `sensor.<p>_cycle_start_snapshot` 💤 | timestamp | When the current/last cycle opened; attributes hold each metric's baseline (`initial_energy`, `initial_cost`, …) |
| `sensor.<p>_cycle_stop_snapshot` 💤 | timestamp | When the last cycle closed; attributes hold the final values (`final_energy`, …) |
| `sensor.<p>_cycle_validation_status` 📈 | — | Verdict on the last closed cycle: `valid`, `too_short`, `too_long`, `too_little_energy`, `too_much_energy` (see [limits](configuration.md#cycle-analytics-cycle_tracking)) |

### Per-metric analytics

Each available metric gets the same four views. Which metrics exist depends on the other families:

| Metric | Requires | Completed / live unit |
| --- | --- | --- |
| `energy` | — | kWh |
| `cost` | `energy_price` | € |
| `energy_from_self`, `energy_from_grid` | `self_sufficiency_source` | kWh |
| `energy_from_grid_savings`, `energy_from_grid_cost` | both | € |

The four views, for each metric `<m>`:

| Entity | Description |
| --- | --- |
| `sensor.<p>_cycle_completed_<m>` 📈 | The metric's value for the **last completed cycle** — its state history is the per-run log |
| `sensor.<p>_cycle_live_<m>` 💤 | The **in-progress** cycle's value so far (0 when idle). For savings/grid-cost the live ids are `_cycle_live_savings_from_grid` / `_cycle_live_cost_from_grid` |
| `sensor.<p>_cycles_<m>_lifetime` 💤 ↺ | Total of the metric accumulated over all *valid* cycles |
| `sensor.<p>_cycles_<m>_mean` 📈 | Average per valid cycle (`lifetime / count`) |

### Duration, count and derived

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_cycles_count_lifetime` 💤 ↺ | cycles | Number of valid completed cycles — also the engine that drives every cycle sensor above |
| `sensor.<p>_cycles_duration_lifetime` 💤 ↺ | s | Total running time over all valid cycles |
| `sensor.<p>_cycle_completed_duration` 📈 | s | Duration of the last completed cycle |
| `sensor.<p>_cycle_live_duration` 💤 | s | Elapsed time of the in-progress cycle (ticks while running) |
| `sensor.<p>_cycles_duration_mean` 📈 | s | Average cycle duration |
| `sensor.<p>_cycles_duration_summary_human` 💤 | — | Total running time formatted for dashboards (`12h 36m`) |
| `sensor.<p>_cycle_completed_self_sufficiency` 📈 | % | Self-sufficiency of the last completed cycle (with `self_sufficiency_source`) |
| `sensor.<p>_cycle_live_self_sufficiency` 💤 | % | Self-sufficiency of the in-progress cycle |
| `sensor.<p>_cycles_self_sufficiency_percentage_mean` 📈 | % | Energy-weighted self-sufficiency across all valid cycles |
| `sensor.<p>_cycle_completed_costovertime` 📈 | €/h | Cost per hour of the last completed cycle (with `energy_price`) |
| `sensor.<p>_cycles_costovertime_mean` 📈 | €/h | Average cost per running hour across all valid cycles |
| `sensor.<p>_cycles_count_<period>` 🚫 | cycles | Lean period meters: how many runs / how much running time per period |
| `sensor.<p>_cycles_duration_<period>` 🚫 | s | ” |

### Events

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

## Standby — requires `standby:` (and `running:` only for the default flavor)

| Entity | Unit | Description |
| --- | --- | --- |
| `binary_sensor.<p>_standby` 📈 | — | The gatekeeper: `on` while the device is in standby, per the configured flavor (`true` = running off; power range; template — see [configuration](configuration.md#standby-standby)). In the default flavor it mirrors `…_running` inverted, so recording both is redundant |
| `sensor.<p>_standby_energy_lifetime` 💤 ↺ | kWh | Energy accumulated **only while `…_standby` is on** — the all-time cost of leaving the device plugged in |
| `sensor.<p>_standby_energy_<period>` 🚫 | kWh | Lean period meters over it |
| `sensor.<p>_standby_duration` 💤 | s | How long the current standby stretch has lasted (0 while not in standby) |
| `sensor.<p>_standby_energy_cost_lifetime` 💤 ↺ | € | Standby energy priced at the current tariff (with `energy_price`) |
| `sensor.<p>_standby_energy_cost_<period>` 🚫 | € | Lean period meters over it |

## Device status — requires `running:` and/or `standby:`

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_status` 📈 | enum | **Presentation-only** label derived from the gatekeepers, handy on dashboards; never consumed by internal logic. States depend on the configured signals: with both, `running` > `standby` > `poweroff`; with running only, `running`/`poweroff`; with standby only, `standby`/`poweron` (out of standby = actively drawing). With the default standby flavor `poweroff` never occurs (it cannot distinguish idle-drawing from truly off). Unavailable whenever a configured gatekeeper is unreadable |
