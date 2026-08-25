# Entity reference

[← Back to README](../README.md)

**Lookup reference**: you see an entity in Home Assistant and want to know what it is, what unlocked it and how the recorder should treat it. If you are instead learning what the integration can do, follow [the levels](../README.md#the-levels) — this page is deliberately flat and assumes no reading order.

## How entity ids are built

```
sensor.<p>_<group>_<metric>_<period>
       │    │       │        └─ one entity per configured period (daily, monthly, …)
       │    │       └────────── what is measured (energy, cost, from_self, …)
       │    └────────────────── which slice (total / running / standby / cycles)
       └─────────────────────── device prefix = <name> + name_suffix (default "_em")
```

A device named `washing_machine` with the default suffix produces `sensor.washing_machine_em_…`.

The `<period>` slot and `lifetime` are **alternatives in the same position**, not something you append: `…_energy_from_self_lifetime` and `…_energy_from_self_daily` are siblings. So the shorthand `<base>_from_self_lifetime` (+ `_<period>`) used in the tables below means *replace* `_lifetime` with the period, never `…_lifetime_daily`.

Supported periods: `hourly`, `daily`, `weekly`, `monthly`, `bimonthly`, `quarterly`, `yearly` — configured per device via `periods:`, defaulting to `[daily, monthly, yearly]`. Anything else is skipped with a warning.

## Markers

Every entity below carries two markers:

- **Recorder class** — how to treat it in the recorder (details in [Recorder Setup](recorder.md)):
  - 🚫 *never record* — a Lean period meter that writes its own long-term statistics; recording it corrupts the series
  - 💤 *exclude* — live view or restore-based accumulator; recording is pure database bloat
  - 📈 *worth recording* — changes at meaningful moments; its state history is useful
- **↺ resettable** — supports the `energy_profiler.reset` entity service. The 🚫 period meters are native Lean entities instead, maintained through Lean's own services — see [Services & Actions](services.md).

## The three energy groups

The core of the model: the same sensor block is built three times over differently-gated slices of the consumption.

| Group | `<base>` | Counts energy… | Exists when | Level |
| --- | --- | --- | --- | --- |
| **Total** | `<p>_energy` | always — any consumption, whatever the device state | always | [1](levels/01-energy.md) |
| **Running** | `<p>_running_energy` | only while `binary_sensor.<p>_running` is on | `running:` | [5](levels/05-running.md) |
| **Standby** | `<p>_standby_energy` | only while `binary_sensor.<p>_standby` is on | `standby:` | [6](levels/06-standby.md) |

The running and standby groups source the **decoupled total lifetime**, so they inherit its reset/plug-swap protection; while their gatekeeper is off *or unavailable* the baseline advances without accumulating, so uncertain periods are never counted. Note the accounting: `total ≈ running + standby + off-residual` only when both gates are configured and never overlap — each group is gated independently, there is no enforced identity.

## The group block

Read this table once and it applies to all three groups: substitute `<base>` with `<p>_energy`, `<p>_running_energy` or `<p>_standby_energy`.

| Entity | Unit | Unlocked by | Description |
| --- | --- | --- | --- |
| `<base>_lifetime` 💤 ↺ | kWh | [L1](levels/01-energy.md) | All-time accumulator for the slice. For the total group this is the **decoupled** total (positive deltas only) every other group and the cycle analytics read from |
| `<base>_<period>` 🚫 | kWh | [L1](levels/01-energy.md) | Lean period meters: live in the UI, one consolidated long-term row per closed period |
| `<base>_from_self_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | [L3](levels/03-self-sufficiency.md) | Share covered by self-production: each delta split by the house flows valid at that instant |
| `<base>_from_grid_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | [L3](levels/03-self-sufficiency.md) | Grid share — the exact remainder of the same atomic split, so `from_self + from_grid` = the total, always |
| `<base>_from_solar_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | [L4](levels/04-solar-battery.md) | Self share coming straight from the panels. Only with a solar channel declared |
| `<base>_from_battery_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | [L4](levels/04-solar-battery.md) | Battery-discharge share — the remainder when both channels exist, so `from_solar + from_battery = from_self` |
| `<base>_cost_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | [L2](levels/02-cost.md) | Cost integrator: each delta priced at the tariff valid *at that moment* |
| `<base>_from_grid_savings_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | [L2](levels/02-cost.md)+[L3](levels/03-self-sufficiency.md) | What self-production saved (the `from_self` share priced) |
| `<base>_from_grid_cost_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | [L2](levels/02-cost.md)+[L3](levels/03-self-sufficiency.md) | What the grid imports actually cost (`from_grid` priced) |
| `<base>_from_self_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | [L3](levels/03-self-sufficiency.md) | `from_self / total`. The `_lifetime` one is all-time; each `_<period>` divides that period's own two meters, written as one long-term point per period |
| `<base>_from_self_index_<period>` 🚫 | × | [L8](levels/08-prosumption.md) | This device's self-sufficiency ÷ the house's, same period. 1.00 = drew at times indistinguishable from the house. Total group only |
| `<base>_from_self_advantage_<period>` 🚫 | kWh | [L8](levels/08-prosumption.md) | Self-produced kWh captured beyond running at the house's own times — the quantity the leaderboard ranks by. Total group only |
| `<base>_from_grid_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | [L3](levels/03-self-sufficiency.md) | The grid's share of the total — the complement of self-sufficiency, as its own gauge |
| `<base>_from_solar_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | [L4](levels/04-solar-battery.md) | Solar share **of the total**. Only when both channels exist — with one, it would duplicate self-sufficiency |
| `<base>_from_battery_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | [L4](levels/04-solar-battery.md) | Battery share of the total. Same condition |

Fully configured, each group is **48 entities** with `[daily, monthly, yearly]`.

**All percentages divide two accumulators**, never average instantaneous readings — so a closed period meter carries the *energy-weighted* share of that period. `from_grid_percentage`, `from_solar_percentage` and `from_battery_percentage` sum to 100, and self-sufficiency is the sum of the last two. There is no "percentage of self" entity: that quantity only ever existed as a configuration input, and no configuration input is a percentage anymore.

**Decimals —** kWh and W rows get their precision from Home Assistant, which derives one from the device class. € and % have no device class default, so the integration supplies one: € shows 2 decimals (configurable via [`cost_precision:`](configuration.md#shared-defaults-defaults)), % shows 1 (fixed). In every case this is display only — the stored state and the long-term statistics keep their full precision, and a precision you set by hand on a single entity overrides it.

## Power

Watts, read straight from the power sensor. Total group only: no gate applies to them.

| Entity | Unit | Unlocked by | Description |
| --- | --- | --- | --- |
| `sensor.<p>_power_max` 📈 ↺ | W | [L1](levels/01-energy.md) | Running peak of the power sensor, kept across restarts until reset |
| `sensor.<p>_power_from_self` 💤 | W | [L3](levels/03-self-sufficiency.md) | Instantaneous share covered by self-production (`power × pct`) |
| `sensor.<p>_power_from_grid` 💤 | W | [L3](levels/03-self-sufficiency.md) | Instantaneous grid share — the exact remainder |
| `sensor.<p>_power_from_solar` 💤 | W | [L4](levels/04-solar-battery.md) | Watts straight from the panels. Only with a solar channel declared |
| `sensor.<p>_power_from_battery` 💤 | W | [L4](levels/04-solar-battery.md) | Battery-discharge watts — the complement inside self |

## Instantaneous cost projections

Euro per unit of time, not euro spent: *"if the draw held at what it is right now, it would cost this much per hour / day / month / year"*. Derived from the power sensors above and the price, so — like them — total group only.

| Entity | Unit | Unlocked by | Description |
| --- | --- | --- | --- |
| `sensor.<p>_energy_cost_instant_<period>` 💤 | € / time | [L2](levels/02-cost.md) | The **whole** draw priced at the import tariff, self-production ignored |
| `sensor.<p>_energy_cost_instant_from_grid_<period>` 💤 | € / time | [L2](levels/02-cost.md)+[L3](levels/03-self-sufficiency.md) | The same over `power_from_grid` instead: what the draw is *actually* costing, once self-production is netted off |

**Which `<period>` variants exist** follows the device's `periods:`, so the projections and the period meters line up by default. `instant_periods:` overrides that independently, and `[]` switches the projections off — see [Configuration](configuration.md#defaults). Each variant is the same €/h rate under a different multiplier, so they differ in nothing but the time unit:

| Period | `hourly` | `daily` | `weekly` | `monthly` | `bimonthly` | `quarterly` | `yearly` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Unit | €/h | €/d | €/w | €/m | €/2m | €/q | €/y |
| Factor | ×1 | ×24 | ×168 | ×720 | ×1440 | ×2160 | ×8760 |

Month and quarter use nominal 30 and 90-day lengths.

The two families answer different questions: **without** `_from_grid` you get the cost of the appliance's consumption as such, **with** it the cost of what you are importing to run it. On a device running entirely on solar the first is non-zero and the second is 0. They mirror `<base>_cost_lifetime` and `<base>_from_grid_cost_lifetime` at the cumulative level; the qualifier trails `cost_instant` rather than sitting in the canonical `_from_grid_` slot so that both families sort together in the UI.

Despite ending in a period name these are **not** period meters — they are instantaneous projections, 💤 rather than 🚫. See [Recorder Setup](recorder.md).

## Gatekeepers and status

| Entity | Unit | Unlocked by | Description |
| --- | --- | --- | --- |
| `binary_sensor.<p>_running` 📈 | — | [L5](levels/05-running.md) | `on` while the appliance runs, per the configured power threshold (with debounce) or template trigger |
| `binary_sensor.<p>_standby` 📈 | — | [L6](levels/06-standby.md) | `on` while in standby, per the configured flavor. In the default flavor it mirrors `…_running` inverted, so recording both is redundant |
| `sensor.<p>_standby_duration` 💤 | s | [L6](levels/06-standby.md) | How long the current standby stretch has lasted (0 while not in standby) |
| `sensor.<p>_status` 📈 | enum | [L5](levels/05-running.md) or [L6](levels/06-standby.md) | **Presentation-only** dashboard label, never consumed by internal logic. With both signals: `running` > `standby` > `poweroff`; with running only: `running`/`poweroff`; with standby only: `standby`/`poweron`. With the default standby flavor `poweroff` never occurs. Unavailable whenever a configured gatekeeper is unreadable |

## Cycles

All from [Level 7](levels/07-cycles.md). Boundary and engine:

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_cycle_start_snapshot` 💤 | timestamp | Marker for the cycle **in progress**: when it opened; attributes hold each metric's baseline (`initial_energy`, …) |
| `sensor.<p>_cycle_stop_snapshot` 💤 | timestamp | Marker for the last close; attributes hold the final values |
| `sensor.<p>_cycle_completed_start` 📈 | timestamp | When the last **valid** cycle started — frozen until the next valid one closes |
| `sensor.<p>_cycle_completed_stop` 📈 | timestamp | When it ended — same freeze |
| `sensor.<p>_cycle_validation_status` 📈 | — | Verdict on the last closed cycle, valid or not: `valid`, `too_short`, `too_long`, `too_little_energy`, `too_much_energy` |
| `sensor.<p>_cycles_count_lifetime` 💤 ↺ (+ `_<period>` 🚫) | cycles | Valid completed runs — also the engine driving every cycle sensor |

The snapshots and the completed pair are **not** interchangeable: the snapshots follow the cycle in progress, so mid-run the start belongs to the running cycle and the stop to the previous one (`start > stop` is how a cycle left open by a restart is detected). Use `_cycle_completed_start` / `_cycle_completed_stop` to describe the last run — see [Level 7](levels/07-cycles.md#what-you-get).

Note the two different populations: the snapshots and `_cycle_validation_status` move on **every** close, while the whole `_cycle_completed_*` family and the counters move only on a **valid** one. A discarded run is therefore visible in the validation status without disturbing any measured value.

Per-metric analytics — each metric has four views (**completed** 📈 last valid run · **live** 💤 in progress · **lifetime** 💤 ↺ all valid runs · **mean** 📈 per valid run):

| Metric | Unlocked by | Unit | Completed | Live | Lifetime | Mean |
| --- | --- | --- | --- | --- | --- | --- |
| energy | [L7](levels/07-cycles.md) | kWh | `…_cycle_completed_energy` | `…_cycle_live_energy` | `…_cycles_energy_lifetime` | `…_cycles_energy_mean` |
| cost | +[L2](levels/02-cost.md) | € | `…_cycle_completed_cost` | `…_cycle_live_cost` | `…_cycles_cost_lifetime` | `…_cycles_cost_mean` |
| from self | +[L3](levels/03-self-sufficiency.md) | kWh | `…_cycle_completed_energy_from_self` | `…_cycle_live_energy_from_self` | `…_cycles_energy_from_self_lifetime` | `…_cycles_energy_from_self_mean` |
| from grid | +[L3](levels/03-self-sufficiency.md) | kWh | `…_cycle_completed_energy_from_grid` | `…_cycle_live_energy_from_grid` | `…_cycles_energy_from_grid_lifetime` | `…_cycles_energy_from_grid_mean` |
| from solar | +[L4](levels/04-solar-battery.md) | kWh | `…_cycle_completed_energy_from_solar` | `…_cycle_live_energy_from_solar` | `…_cycles_energy_from_solar_lifetime` | `…_cycles_energy_from_solar_mean` |
| from battery | +[L4](levels/04-solar-battery.md) | kWh | `…_cycle_completed_energy_from_battery` | `…_cycle_live_energy_from_battery` | `…_cycles_energy_from_battery_lifetime` | `…_cycles_energy_from_battery_mean` |
| savings | +[L2](levels/02-cost.md)+[L3](levels/03-self-sufficiency.md) | € | `…_cycle_completed_energy_from_grid_savings` | `…_cycle_live_savings_from_grid` | `…_cycles_energy_from_grid_savings_lifetime` | `…_cycles_energy_from_grid_savings_mean` |
| grid cost | +[L2](levels/02-cost.md)+[L3](levels/03-self-sufficiency.md) | € | `…_cycle_completed_energy_from_grid_cost` | `…_cycle_live_cost_from_grid` | `…_cycles_energy_from_grid_cost_lifetime` | `…_cycles_energy_from_grid_cost_mean` |

(`…` = `sensor.<p>`. Note the two irregular live ids for savings and grid cost.)

Duration and derived:

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_cycles_duration_lifetime` 💤 ↺ (+ `_<period>` 🚫) | s | Total running time over all valid cycles |
| `sensor.<p>_cycle_completed_duration` 📈 | s | Duration of the last completed cycle |
| `sensor.<p>_cycle_live_duration` 💤 | s | Elapsed time of the in-progress cycle |
| `sensor.<p>_cycles_duration_mean` 📈 | s | Average cycle duration |
| `sensor.<p>_cycles_duration_summary_human` 💤 | — | Total running time formatted for dashboards (`12h 36m`) |
| `sensor.<p>_cycle_completed_from_self_percentage` 📈 | % | Self-sufficiency of the last completed cycle |
| `sensor.<p>_cycle_live_from_self_percentage` 💤 | % | Self-sufficiency of the in-progress cycle |
| `sensor.<p>_cycles_from_self_percentage_mean` 📈 | % | Energy-weighted self-sufficiency across all valid cycles |
| `sensor.<p>_cycle_completed_costovertime` 📈 | €/h | Cost per hour of the last completed cycle |
| `sensor.<p>_cycles_costovertime_mean` 📈 | €/h | Average cost per running hour across all valid cycles |

Battery coverage estimate (only when `battery_available_energy` and cycle tracking are both configured):

| Entity | Unit | Description |
| --- | --- | --- |
| `binary_sensor.<p>_battery_can_cover_average_cycle` 💤 | — | `on` when current usable battery kWh cover `…_cycles_energy_mean`. Unavailable without a valid non-zero cycle or readable inputs; attributes include both values, margin, average cycles covered and sample count |

Cycle events (`energy_profiler_cycle_completed` / `_cycle_discarded`) and their payload are documented in [Level 7](levels/07-cycles.md#events).

## The global devices

### Energy Profiler (system)

The integration root owns its diagnostic plus every global house entity except the three percentage families separated below; every appliance and each dedicated score device are attached through `via_device`.

| Entity | Unit | Unlocked by | Description |
| --- | --- | --- | --- |
| `energy_profiler_configuration` 📈 | — | always | Diagnostic: profiled device count, with the declared config in the attributes |
| `energy_profiler_from_self_percentage` 💤 | % | `power_flows` | The house self share **right now**. Instantaneous — not comparable with the per-device period figures |
| `energy_profiler_from_grid_percentage` 💤 | % | `power_flows` | The grid's share right now |
| `energy_profiler_from_solar/battery_percentage` 💤 | % | 2 channels | Each channel's share of the house load right now |
| `energy_profiler_self_energy_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | `energy_flows` | `E_self`: consumption not imported — identically, production not exported |
| `energy_profiler_consumption_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | `energy_flows` | House consumption observed by the integration; denominator of self-sufficiency and reusable in dashboards |
| `energy_profiler_production_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | + `production` | House production observed by the integration; denominator of self-consumption/prosumption and reusable in dashboards |
| `energy_profiler_energy_balance` 📈 | kWh | all four | Diagnostic: the two readings of `E_self` must agree; drift means a meter is wrong |
| `energy_profiler_self_ranking_<period>` 💤 | — | `energy_flows` | The leaderboard: leading device as state, ordered table in the attributes |

### The three score devices

Each global percentage family is attached to its own dedicated child device:

| Device | Entity | Unit | Unlocked by | Description |
| --- | --- | --- | --- | --- |
| **Energy Profiler (self-sufficiency)** | `energy_profiler_self_sufficiency_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | `energy_flows` | `E_self / consumption` — **the baseline** every per-device comparison divides by |
| **Energy Profiler (self-consumption)** | `energy_profiler_self_consumption_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | + `production` | `E_self / production` |
| **Energy Profiler (prosumption)** | `energy_profiler_prosumption_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | + `production` | `E_self / min(consumption, production)` — measured against whichever side was scarce |

Each `_<period>` score also has a hidden `…_<period>_live` companion. It exists only to give the period meter something to mirror, carries no state class and writes no statistics — see [Level 8 → Recorder](levels/08-prosumption.md#recorder).

## Totals

Entity count for a fully-configured device with the default `[daily, monthly, yearly]` periods — fewer options, or fewer periods, mean fewer entities:

| Block | Entities | Level |
| --- | --- | --- |
| Power + total energy group | 59 | [1](levels/01-energy.md)–[4](levels/04-solar-battery.md) |
| Running signal + running energy group | 49 | [5](levels/05-running.md) |
| Standby gatekeeper, duration + standby energy group | 50 | [6](levels/06-standby.md) |
| Cycle analytics + battery coverage estimate | 55 | [7](levels/07-cycles.md) |
| Status label | 1 | [5](levels/05-running.md)/[6](levels/06-standby.md) |
| Baseline comparison (index + advantage) | 6 | [8](levels/08-prosumption.md) |
| **Total** | **220** | |

94 of those are fixed and 46 scale with the number of configured periods. Without `battery_available_energy`, subtract one fixed entity; with `include_in_ranking: false`, omit the six public baseline-comparison meters (and their hidden live helpers).

The four global devices add **29 more entities altogether, once for the whole system** (14 without `production:`), plus the ones `power_flows` already brought.
