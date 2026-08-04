# Configuration

[← Back to README](../README.md)

Everything lives under a single `energy_profiler:` block: one global `defaults` section plus a `devices` list. What each device enables is decided by **which options it declares** — there are no `enable_x: true` switches:

| You provide… | You get |
| --- | --- |
| `power` + `energy` (required) | peak power + the **total energy group** — all-time total, per-period energy meters |
| `energy_price` | the **cost sub-block** in every energy group (€ accumulators, per-period cost meters) + instant cost rates on the total |
| `power_flows:` with `grid` + `load` | the **self/grid split sub-block** in every energy group (power, energy, %), and with a price also savings/grid-cost |
| `power_flows:` also with `battery` (or `solar`) | the **solar/battery split** of the self share (`from_solar` + `from_battery` = `from_self`) in every group and in the cycle metrics |
| `running:` block | the running **signal** (`binary_sensor.<prefix>_running`) plus the **running energy group** — the same stack as the total, gated on it |
| `cycle_tracking:` (needs `running:`) | **cycles** family — per-run analytics: completed/live/mean values, counters, events |
| `standby:` (bool or trigger block) | the standby **signal** (`binary_sensor.<prefix>_standby`) plus the **standby energy group** — same stack, gated on it |
| `running:` and/or `standby:` | also `sensor.<prefix>_status` — a presentation-only enum label (`running`/`standby`/`poweroff`/`poweron`) for dashboards |
| `energy_flows:` with `consumption` + `import` | the **house self-sufficiency** and the **baseline**; with `power_flows` too, each device's `index` and `advantage` and the **leaderboard** |
| `energy_flows:` also with `production` | **self-consumption** and **prosumption** — the two house scores measured against the generation side |

Two vocabulary notes, deliberate and consistent across docs and entities:

- **periods** are the Lean meter windows (`daily`, `monthly`, …) — the `periods` option;
- **cycles** are appliance runs (a wash program, an A/C session) — the `running:` signal and the `cycle_tracking:` analytics.

The full entity output of each family is cataloged in [Entities](entities.md).

**Splitting across packages:** Home Assistant merges the domain natively. Put `defaults:` in exactly one file and spread `devices:` across as many package files as you like — the device lists are concatenated and validated as a whole.

## Shared defaults (`defaults:`)

Global values inherited by every device that does not override them.

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `energy_price` | entity id | — | Sensor with the current energy purchase price (€/kWh). Enables the **cost** family for all devices |
| `power_flows` | mapping | — | The house flows in W the per-device split is derived from. See [Power flows](#power-flows-power_flows) below |
| `energy_flows` | mapping | — | The house kWh counters the prosumption scores are built from. **No per-device form** — see [Energy flows](#energy-flows-energy_flows) below |
| `name_suffix` | string | `_em` | Appended to each device `name` to form the entity prefix (`<name><name_suffix>`); useful to namespace the whole fleet |
| `live_update_interval` | duration | `00:05:00` | Throttle for the Lean meters' live LTS upserts (period boundaries are always written exactly). Passed through to every meter |
| `periods` | list | `[daily, monthly, yearly]` | Which per-period meters every device gets: `hourly`, `daily`, `weekly`, `monthly`, `bimonthly`, `quarterly`, `yearly` |
| `instant_periods` | list | follows `periods` | Which [instantaneous cost projections](entities.md#instantaneous-cost-projections) to build. Same vocabulary as `periods`. Omit to keep the two aligned; `[]` switches the projections off |
| `cost_precision` | integer 0–10 | `2` | Decimals **shown** by the € entities. Display only: the cost accumulators integrate in `Decimal` and are never rounded, so no cent is ever gained or lost — this only caps the decimals the UI renders. A precision you set by hand on a single entity still wins over it |

## Device base options

| Option | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | slug | ✔ | Device slug; with `name_suffix` it forms the prefix of every entity id (`washing_machine` → `sensor.washing_machine_em_…`) |
| `power` | entity id | ✔ | The device's instantaneous power sensor (W) |
| `energy` | entity id | ✔ | The device's cumulative energy sensor (kWh). Resets and sensor swaps are tolerated: the integration accumulates only positive deltas into its own lifetime total |
| `energy_price` | entity id or `null` | — | Per-device override of the default. Set `null` to opt this device **out** of the cost family even when a default is configured |
| `power_flows` | mapping or `null` | — | Per-device override; `null` opts out of the split entirely. Replaced **wholesale**, never merged key by key — a half-inherited block would mix two houses' readings |
| `live_update_interval` | duration | — | Per-device override of the default |
| `periods` | list | — | Per-device override of the default period set |
| `instant_periods` | list | — | Per-device override; when unset the device falls back to its own `periods` |
| `cost_precision` | integer 0–10 | — | Per-device override of the default |

## Power flows (`power_flows:`)

The base readings the whole per-device split is derived from, in **watts**. The integration never asks for a percentage: it computes the shares from these on every tick, and publishes the percentages back as entities.

| Key | Required | Meaning |
| --- | --- | --- |
| `grid` | ✔ | Power the house is importing from the grid |
| `load` | one of the two | Total house consumption. The solar contribution is derived from it as the remainder |
| `solar` | one of the two | Power the panels are delivering **to the load** — not the raw production |
| `battery` | — | Battery **discharge** power. Declaring it enables the solar/battery channels |

```yaml
power_flows:
  load: sensor.house_load_power
  grid: sensor.grid_import_power
  battery: sensor.battery_discharge_power
  # solar: — absent on purpose: derived as load − grid − battery.
```

The solar contribution is the one you will most likely *not* declare, even though it is the channel Level 4 is named after. That is deliberate: `solar` must be solar-to-load, and almost no inverter publishes it — what it publishes is production, which also charges the battery and feeds the export. Deriving it from `load` gets the right number from readings you actually have, and guarantees the portions sum to the load.

The explicit form, for the rare setup that does expose it:

```yaml
power_flows:
  grid: sensor.grid_import_power
  solar: sensor.solar_to_load_power
  battery: sensor.battery_discharge_power
```

### What the numbers must mean

Each flow is a **contribution to the house load**, and the ones you declare must add up to it. That rules out three tempting substitutions:

- **Raw solar production instead of solar-to-load.** Production also charges the battery and feeds the export, so it overstates the solar share exactly when production is highest. This is what `load:` is for: derived from the remainder, the solar contribution cannot be wrong in that way.
- **Net grid exchange instead of import.** A sensor that goes negative while exporting is fine — negatives are clamped to zero. One that reports import minus export as a single signed number is not: while you export it reads negative, and the split sees zero grid.
- **Signed battery power read as discharge.** Negative-while-charging is fine (clamped); positive-while-charging would be counted as if the battery were feeding the house.

### Validation

Two shapes are rejected at load time rather than silently resolved, because either would skew every device with no visible symptom:

- `load` **and** `solar` together — over-specified, since `load` exists precisely to derive `solar`. Drop one.
- `grid` alone, with no `load` and no channel — every device would come out 100% grid-fed.

### What gets built

| Declared | Channels | `from_self` |
| --- | --- | --- |
| `load` + `grid` | — | the unqualified self share |
| `load` + `grid` + `battery` | solar, battery | `from_solar + from_battery` |
| `grid` + `solar` | solar | `from_solar` |
| `grid` + `battery` | battery | `from_battery` |
| `grid` + `solar` + `battery` | solar, battery | `from_solar + from_battery` |

Nothing is created that would only ever read zero: no battery flow means no battery entities. With a single channel, `from_self` and that channel hold the same number and both exist — `from_self` is what the monetary view prices, the channel is the one named for what happened — but the channel *percentage* is not created, since it would duplicate self-sufficiency.

If the flows are unreadable at a given tick, the whole delta is attributed to the grid. A broken sensor can understate your self-production; it can never inflate it, nor the savings computed from it.

## Energy flows (`energy_flows:`)

The house **kWh counters**, for [Level 8](levels/08-prosumption.md). A separate block from `power_flows`, and a different kind of input: totals rather than watts, and including the two readings `power_flows` deliberately keeps out — raw production and export.

```yaml
defaults:
  energy_flows:
    consumption: sensor.house_consumption_energy_total   # required
    import:      sensor.grid_import_energy_total         # required
    production:  sensor.pv_production_energy_total       # optional
    export:      sensor.grid_export_energy_total         # optional
```

| Option | Required | Meaning |
| --- | --- | --- |
| `consumption` | ✔ | Total house consumption, all-time |
| `import` | ✔ | Energy drawn from the grid, all-time |
| `production` | | Raw output of the panels, all-time |
| `export` | | Energy fed into the grid, all-time |

### Why these two are required and those two are not

The house obeys `consumption = production + import − export`, so the self-consumed energy has two equivalent readings:

```
E_self = consumption − import = production − export
```

`consumption` and `import` are required because their difference *is* `E_self` and their ratio *is* the baseline. `production` is the only genuinely new denominator, and it unlocks self-consumption and prosumption. `export` adds no information at all — `E_self` is already known without it — so its sole job is the cross-check: with all four declared, `sensor.energy_profiler_energy_balance` publishes how far the two readings disagree, which should be noise around zero.

### What the counters must be

- **Monotonic totals**, not per-period sensors. The integration builds its own meters on your `periods:`; a counter that resets at midnight reads as a broken meter at every rollover.
- **`import` and `export` separate**, never one signed net figure. A sensor that goes negative on export counts exports as negative imports and corrupts `E_self`.
- **kWh.** No unit conversion is performed.

### Why it has no per-device form

These are readings of the whole house. A device overriding them would be claiming a second house rather than a different view of this one — so unlike `power_flows`, `energy_flows:` is rejected inside a device block. What a device takes from it is only the *baseline* to be compared against, which is the same for all of them by construction.

Production in particular cannot be split per device at all: the only defensible apportionment makes every appliance score the identical house figure. [Level 8](levels/08-prosumption.md#production-cannot-be-given-to-a-device--and-the-reason-is-not-its-hard) works the algebra.

## Running detection (`running:`)

A **signal**: declaring it creates `binary_sensor.<prefix>_running` and enables the **running energy group** — the same energy/split/cost stack as the total, accumulated only while running (see [Entity reference](entities.md#the-three-energy-groups), or [Level 5](levels/05-running.md) for the guided version). Other consumers hang on the signal explicitly: [`cycle_tracking:`](#cycle-analytics-cycle_tracking) for run analytics, and the default flavor of [`standby:`](#standby-standby). Unlike the cycles family, the running group counts *every* running moment, validated or not — it is what lets you split running vs standby consumption without tracking cycles.

Two trigger flavors:

**Power threshold** — for appliances recognizable by their draw:

```yaml
running:
  trigger: power
  on_above: 5          # W: running when power rises above this…
  on_delay: "00:00:30" # …for at least this long (default 0 = immediately)
  off_below: 2         # W: stopped when power falls below this…
  off_delay: "00:02:00"# …for at least this long (default 0)
```

| Option | Default | Meaning |
| --- | --- | --- |
| `on_above` | `0` | power (W) above which the device counts as running |
| `off_below` | `1` | power (W) below which it counts as stopped |
| `on_delay` | `00:00:00` | how long the power must stay above `on_above` before turning on (debounces spikes) |
| `off_delay` | `00:00:00` | how long it must stay below `off_below` before turning off (bridges intra-run pauses, e.g. a dishwasher heating phase) |

**Template** — when a better signal than power exists (a `climate` state, a helper, …):

```yaml
running:
  trigger: template
  available: "{{ has_value('climate.bedroom_ac') }}"
  state: "{{ states('climate.bedroom_ac') != 'off' }}"
```

| Option | Required | Meaning |
| --- | --- | --- |
| `state` | ✔ | template that renders truthy while the device is running |
| `available` | ✔ | template that renders truthy when the signal itself is trustworthy; while false the running sensor goes unavailable instead of guessing |

## Cycle analytics (`cycle_tracking:`)

The analytics **consumer** of the running signal: counts each run with its duration, energy, cost, solar split, … (the full output is in [Level 7 — Cycles](levels/07-cycles.md)). Requires `running:`; without it the family is skipped with a warning.

```yaml
cycle_tracking: true          # analytics, no plausibility limits
# or
cycle_tracking:
  limits:
    min_duration: "00:05:00"
    max_duration: "12:00:00"
    min_energy: 0.05   # kWh
    max_energy: 10.0   # kWh
```

`limits` are optional plausibility checks applied when a run ends. A run failing any of them is **discarded**: its snapshot/completed/validation sensors are still written (so you can inspect it), but it does not increment the counters, totals or means, and the `…_cycle_discarded` event fires instead of `…_cycle_completed`.

| Limit | Rejected as |
| --- | --- |
| `min_duration` | `too_short` |
| `max_duration` | `too_long` |
| `min_energy` | `too_little_energy` |
| `max_energy` | `too_much_energy` |

The verdict (or `valid`) is exposed by `sensor.<prefix>_cycle_validation_status` and in the event payload.

## Standby (`standby:`)

Enables the **standby energy group**: the full energy stack (energy, solar/grid split, costs, self-sufficiency % — same block as the total and running groups) accumulated while the device is in standby, gated on a dedicated `binary_sensor.<prefix>_standby`, plus the live `…_standby_duration`. Three gatekeeper flavors:

**Default** — standby is simply "not running". Requires the `running:` block (without the signal there is no notion of "idle"; the family is skipped with a warning) — but **not** `cycle_tracking`: a device can define running purely to give standby its complement. The standby sensor mirrors `…_running` inverted, and follows its availability:

```yaml
standby: true
```

**Power threshold** — standby while the draw sits in the vampire range. Does **not** require `running:`. Thresholds are inverted with respect to `running:` (standby is entered going *down*):

```yaml
standby:
  trigger: power
  on_below: 8            # W: standby when power drops below this…
  on_delay: "00:01:00"   # …for at least this long (default 0)
  off_above: 12          # W: standby ends above this (default: same as on_below)
  off_delay: "00:00:10"  # …for at least this long (default 0)
```

**Template** — any custom condition (a `media_player` state, a helper, …). Does **not** require `running:`:

```yaml
standby:
  trigger: template
  available: "{{ has_value('media_player.console') }}"
  state: "{{ is_state('media_player.console', 'standby') }}"
```

Whatever the flavor, energy is attributed to standby only while the gatekeeper is `on` — when it is `off` **or unavailable**, the baseline advances without accumulating, so uncertain periods are never counted as standby.

## Full example

See [`examples/full.yaml`](../examples/full.yaml) for a fleet mixing all of the above: shared defaults, a plain consumption device, a solar-split device, a cycle-tracked washing machine with limits, a TV with running + standby but no analytics, and a stereo with standalone standby.
