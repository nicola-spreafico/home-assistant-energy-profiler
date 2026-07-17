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

## Energy groups — total, running, standby

Energy comes in three **groups**, symmetric by construction: each is the same sensor block over a differently-gated slice of the consumption. `<base>` below stands for the group base id:

| Group | `<base>` | Counts energy… | Exists when |
| --- | --- | --- | --- |
| **Total** | `<p>_energy` | always — any consumption, whatever the device state | always |
| **Running** | `<p>_running_energy` | only while `binary_sensor.<p>_running` is on | `running:` configured |
| **Standby** | `<p>_standby_energy` | only while `binary_sensor.<p>_standby` is on | `standby:` configured |

The running and standby groups source the **decoupled total lifetime**, so they inherit its reset/plug-swap protection; while their gatekeeper is off *or unavailable* the baseline advances without accumulating, so uncertain periods are never counted. Note the accounting: `total ≈ running + standby + off-residual` only when both gates are configured and never overlap — each group is gated independently, there is no enforced identity.

**The common block**, per group (sub-blocks appear when their requirement is met):

| Entity | Unit | Requires | Description |
| --- | --- | --- | --- |
| `sensor.<base>_lifetime` 💤 ↺ | kWh | — | The group's all-time accumulator. For the total group this is the decoupled source everything else reads from |
| `sensor.<base>_<period>` 🚫 | kWh | — | Lean period meters: live counter in the UI, one consolidated LTS row per closed period |
| `sensor.<base>_from_self_lifetime` 💤 ↺ | kWh | `self_sufficiency_source` | Share covered by self-production: each group delta split by the current self-sufficiency % |
| `sensor.<base>_from_grid_lifetime` 💤 ↺ | kWh | ” | Grid share — the exact remainder of the same atomic split, so `from_self + from_grid` = the group total, always |
| `sensor.<base>_from_self_<period>` / `_from_grid_<period>` 🚫 | kWh | ” | Lean period meters over the split |
| `sensor.<base>_from_solar_lifetime` / `_from_battery_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | `self_sufficiency_source` + a share source | Second-level split of the self share: direct solar vs battery discharge, driven by `solar_share_source` (or `battery_share_source`, the complement). `from_solar + from_battery = from_self`, always |
| `sensor.<base>_cost_lifetime` 💤 ↺ | € | `energy_price` | Cost integrator: each delta priced at the tariff valid *at that moment* |
| `sensor.<base>_cost_<period>` 🚫 | € | ” | Lean period meters over the cost |
| `sensor.<base>_from_grid_savings_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | both | What self-production saved (the `from_self` share priced) |
| `sensor.<base>_from_grid_cost_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | both | What the grid imports actually cost (`from_grid` priced) |
| `sensor.<base>_self_sufficiency_lifetime` 💤 (+ `_<period>` 🚫) | % | `self_sufficiency_source` | Live ratio `from_self / total` of the group; the period meters snapshot it as a gauge (one LTS point per period) |

**Total group extras** — the instantaneous cost projections (`power × price`, no gate applies):

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_cost_instant_hourly` 💤 | €/h | Projected cost rate if the current draw held for an hour |
| `sensor.<p>_energy_cost_instant_daily` / `_monthly` / `_yearly` 💤 | €/d, €/m, €/y | Same projection over a day / 30-day month / year |

**Standby group extras**:

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_standby_duration` 💤 | s | How long the current standby stretch has lasted (0 while not in standby) |

## Cycles — requires `running:` and `cycle_tracking:`

### Run detection and cycle boundary

| Entity | Unit | Description |
| --- | --- | --- |
| `binary_sensor.<p>_running` 📈 | — | The gatekeeper: `on` while the appliance runs, according to the configured power threshold or template trigger. Created by `running:` alone (it is the signal); cycle open/close, the running-energy group and default-flavor standby all follow it |
| `sensor.<p>_cycle_start_snapshot` 💤 | timestamp | When the current/last cycle opened; attributes hold each metric's baseline (`initial_energy`, `initial_cost`, …) |
| `sensor.<p>_cycle_stop_snapshot` 💤 | timestamp | When the last cycle closed; attributes hold the final values (`final_energy`, …) |
| `sensor.<p>_cycle_validation_status` 📈 | — | Verdict on the last closed cycle: `valid`, `too_short`, `too_long`, `too_little_energy`, `too_much_energy` (see [limits](configuration.md#cycle-analytics-cycle_tracking)) |

### Per-metric analytics

Each available metric gets the same four views. Which metrics exist depends on the configured sources:

| Metric | Requires | Completed / live unit |
| --- | --- | --- |
| `energy` | — | kWh |
| `cost` | `energy_price` | € |
| `energy_from_self`, `energy_from_grid` | `self_sufficiency_source` | kWh |
| `energy_from_solar`, `energy_from_battery` | `self_sufficiency_source` + a share source | kWh |
| `energy_from_grid_savings`, `energy_from_grid_cost` | `self_sufficiency_source` + `energy_price` | € |

The four views, for each metric `<m>`:

| Entity | Description |
| --- | --- |
| `sensor.<p>_cycle_completed_<m>` 📈 | The metric's value for the **last completed cycle** — its state history is the per-run log |
| `sensor.<p>_cycle_live_<m>` 💤 | The **in-progress** cycle's value so far (0 when idle). For savings/grid-cost the live ids are `_cycle_live_savings_from_grid` / `_cycle_live_cost_from_grid` |
| `sensor.<p>_cycles_<m>_lifetime` 💤 ↺ | Total of the metric accumulated over all *valid* cycles (a discarded run counts in the energy groups but not here) |
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

## Standby gatekeeper — requires `standby:`

| Entity | Unit | Description |
| --- | --- | --- |
| `binary_sensor.<p>_standby` 📈 | — | The gatekeeper: `on` while the device is in standby, per the configured flavor (`true` = running off; power range; template — see [configuration](configuration.md#standby-standby)). The standby energy group gates on it. In the default flavor it mirrors `…_running` inverted, so recording both is redundant |

## Device status — requires `running:` and/or `standby:`

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_status` 📈 | enum | **Presentation-only** label derived from the gatekeepers, handy on dashboards; never consumed by internal logic. States depend on the configured signals: with both, `running` > `standby` > `poweroff`; with running only, `running`/`poweroff`; with standby only, `standby`/`poweron` (out of standby = actively drawing). With the default standby flavor `poweroff` never occurs (it cannot distinguish idle-drawing from truly off). Unavailable whenever a configured gatekeeper is unreadable |

## Appendix — full entity inventory

The explicit, exhaustive list for a **fully-configured device** (`energy_price` + `self_sufficiency_source` + a share source + `running:` + `cycle_tracking:` + `standby:`). Devices with fewer options simply lose the corresponding lines. `<period>` expands to one entity per configured period — with the default `[daily, monthly, yearly]` a fully-equipped device totals **171 entities** (84 fixed + 29 per period).

**Gatekeepers & status (3)**

- `binary_sensor.<p>_running`
- `binary_sensor.<p>_standby`
- `sensor.<p>_status`

**Power (3)**

- `sensor.<p>_power_max`
- `sensor.<p>_power_from_self`
- `sensor.<p>_power_from_grid`

**Energy groups (3 × (9 + 9·periods), + 4 instant, + 1 standby duration)** — for each `<base>` ∈ `<p>_energy`, `<p>_running_energy`, `<p>_standby_energy`:

- `sensor.<base>_lifetime` — and `sensor.<base>_<period>`
- `sensor.<base>_from_self_lifetime` — and `sensor.<base>_from_self_<period>`
- `sensor.<base>_from_grid_lifetime` — and `sensor.<base>_from_grid_<period>`
- `sensor.<base>_from_solar_lifetime` — and `sensor.<base>_from_solar_<period>`
- `sensor.<base>_from_battery_lifetime` — and `sensor.<base>_from_battery_<period>`
- `sensor.<base>_cost_lifetime` — and `sensor.<base>_cost_<period>`
- `sensor.<base>_from_grid_savings_lifetime` — and `sensor.<base>_from_grid_savings_<period>`
- `sensor.<base>_from_grid_cost_lifetime` — and `sensor.<base>_from_grid_cost_<period>`
- `sensor.<base>_self_sufficiency_lifetime` — and `sensor.<base>_self_sufficiency_<period>`

plus, total group only:

- `sensor.<p>_energy_cost_instant_hourly` / `_daily` / `_monthly` / `_yearly`

plus, standby group only:

- `sensor.<p>_standby_duration`

**Cycles (46 + 2·periods)**

Boundary and engine:

- `sensor.<p>_cycle_start_snapshot`
- `sensor.<p>_cycle_stop_snapshot`
- `sensor.<p>_cycle_validation_status`
- `sensor.<p>_cycles_count_lifetime` — and `sensor.<p>_cycles_count_<period>`

Per-metric views (8 metrics × 4 views):

| Metric | Completed | Live | Lifetime over valid cycles | Mean |
| --- | --- | --- | --- | --- |
| energy | `…_cycle_completed_energy` | `…_cycle_live_energy` | `…_cycles_energy_lifetime` | `…_cycles_energy_mean` |
| cost | `…_cycle_completed_cost` | `…_cycle_live_cost` | `…_cycles_cost_lifetime` | `…_cycles_cost_mean` |
| from_self | `…_cycle_completed_energy_from_self` | `…_cycle_live_energy_from_self` | `…_cycles_energy_from_self_lifetime` | `…_cycles_energy_from_self_mean` |
| from_grid | `…_cycle_completed_energy_from_grid` | `…_cycle_live_energy_from_grid` | `…_cycles_energy_from_grid_lifetime` | `…_cycles_energy_from_grid_mean` |
| from_solar | `…_cycle_completed_energy_from_solar` | `…_cycle_live_energy_from_solar` | `…_cycles_energy_from_solar_lifetime` | `…_cycles_energy_from_solar_mean` |
| from_battery | `…_cycle_completed_energy_from_battery` | `…_cycle_live_energy_from_battery` | `…_cycles_energy_from_battery_lifetime` | `…_cycles_energy_from_battery_mean` |
| savings | `…_cycle_completed_energy_from_grid_savings` | `…_cycle_live_savings_from_grid` | `…_cycles_energy_from_grid_savings_lifetime` | `…_cycles_energy_from_grid_savings_mean` |
| grid cost | `…_cycle_completed_energy_from_grid_cost` | `…_cycle_live_cost_from_grid` | `…_cycles_energy_from_grid_cost_lifetime` | `…_cycles_energy_from_grid_cost_mean` |

Duration and derived:

- `sensor.<p>_cycles_duration_lifetime` — and `sensor.<p>_cycles_duration_<period>`
- `sensor.<p>_cycle_completed_duration`
- `sensor.<p>_cycle_live_duration`
- `sensor.<p>_cycles_duration_mean`
- `sensor.<p>_cycles_duration_summary_human`
- `sensor.<p>_cycle_completed_self_sufficiency`
- `sensor.<p>_cycle_live_self_sufficiency`
- `sensor.<p>_cycles_self_sufficiency_percentage_mean`
- `sensor.<p>_cycle_completed_costovertime`
- `sensor.<p>_cycles_costovertime_mean`
