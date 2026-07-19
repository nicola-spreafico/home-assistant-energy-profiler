# Level 7 — Cycles

[← Level 6: Standby](06-standby.md) · [The levels](../../README.md#the-levels)

> *"Did yesterday's wash actually run on sunshine, or did it silently pull half its load from the grid — and what did that one run cost?"*

The top of the path. Everything so far measured *periods*; this measures **individual runs**. Each completed cycle gets its own energy, cost, solar share and duration, with means and lifetime totals across all valid runs — plus bus events to automate on.

**Prerequisites:** [Level 5](05-running.md) — the analytics consume the running signal. Configuring `cycle_tracking:` without `running:` is skipped with a warning.

## Minimum configuration

```yaml
energy_profiler:
  devices:
    - name: washing_machine
      power: sensor.washing_machine_power
      energy: sensor.washing_machine_energy
      running:
        trigger: power
        on_above: 5
        on_delay: "00:00:30"
        off_below: 2
        off_delay: "00:02:00"
      cycle_tracking: true          # analytics, no plausibility limits
```

With **limits**, so implausible runs are discarded instead of polluting the means:

```yaml
      cycle_tracking:
        limits:
          min_duration: "00:05:00"
          max_duration: "04:00:00"
          min_energy: 0.05          # kWh
          max_energy: 5.0
```

A run outside the limits is recorded as discarded: counters and means are left untouched, though its energy still counts in the [running group](05-running.md).

## What you get

**Boundary and engine:**

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_cycle_start_snapshot` 💤 | timestamp | When the current/last cycle opened; attributes hold each metric's baseline (`initial_energy`, `initial_cost`, …) |
| `sensor.<p>_cycle_stop_snapshot` 💤 | timestamp | When the last cycle closed; attributes hold the final values |
| `sensor.<p>_cycle_validation_status` 📈 | — | Verdict on the last closed cycle: `valid`, `too_short`, `too_long`, `too_little_energy`, `too_much_energy` |
| `sensor.<p>_cycles_count_lifetime` 💤 ↺ (+ `_<period>` 🚫) | cycles | Valid completed runs — also the engine driving every sensor on this page |

**Per-metric analytics.** Every available metric gets the **same four views**:

- **Completed** 📈 — value for the last completed cycle; its state history *is* your per-run log
- **Live** 💤 — the in-progress cycle so far (0 when idle)
- **Lifetime** 💤 ↺ — total over all valid cycles
- **Mean** 📈 — average per valid cycle (`lifetime / count`)

Which metrics exist scales with the levels you configured:

| Metric | Requires | Unit | Completed | Live | Lifetime | Mean |
| --- | --- | --- | --- | --- | --- | --- |
| energy | — | kWh | `…_cycle_completed_energy` | `…_cycle_live_energy` | `…_cycles_energy_lifetime` | `…_cycles_energy_mean` |
| cost | [L2](02-cost.md) | € | `…_cycle_completed_cost` | `…_cycle_live_cost` | `…_cycles_cost_lifetime` | `…_cycles_cost_mean` |
| from self | [L3](03-self-sufficiency.md) | kWh | `…_cycle_completed_energy_from_self` | `…_cycle_live_energy_from_self` | `…_cycles_energy_from_self_lifetime` | `…_cycles_energy_from_self_mean` |
| from grid | [L3](03-self-sufficiency.md) | kWh | `…_cycle_completed_energy_from_grid` | `…_cycle_live_energy_from_grid` | `…_cycles_energy_from_grid_lifetime` | `…_cycles_energy_from_grid_mean` |
| from solar | [L4](04-solar-battery.md) | kWh | `…_cycle_completed_energy_from_solar` | `…_cycle_live_energy_from_solar` | `…_cycles_energy_from_solar_lifetime` | `…_cycles_energy_from_solar_mean` |
| from battery | [L4](04-solar-battery.md) | kWh | `…_cycle_completed_energy_from_battery` | `…_cycle_live_energy_from_battery` | `…_cycles_energy_from_battery_lifetime` | `…_cycles_energy_from_battery_mean` |
| savings | [L2](02-cost.md)+[L3](03-self-sufficiency.md) | € | `…_cycle_completed_energy_from_grid_savings` | `…_cycle_live_savings_from_grid` | `…_cycles_energy_from_grid_savings_lifetime` | `…_cycles_energy_from_grid_savings_mean` |
| grid cost | [L2](02-cost.md)+[L3](03-self-sufficiency.md) | € | `…_cycle_completed_energy_from_grid_cost` | `…_cycle_live_cost_from_grid` | `…_cycles_energy_from_grid_cost_lifetime` | `…_cycles_energy_from_grid_cost_mean` |

(`…` = `sensor.<p>`. Note the two irregular live ids for savings and grid cost.)

**Duration and derived:**

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_cycles_duration_lifetime` 💤 ↺ (+ `_<period>` 🚫) | s | Total running time over all valid cycles |
| `sensor.<p>_cycle_completed_duration` 📈 | s | Duration of the last completed cycle |
| `sensor.<p>_cycle_live_duration` 💤 | s | Elapsed time of the in-progress cycle |
| `sensor.<p>_cycles_duration_mean` 📈 | s | Average cycle duration |
| `sensor.<p>_cycles_duration_summary_human` 💤 | — | Total running time formatted for dashboards (`12h 36m`) |
| `sensor.<p>_cycle_completed_self_sufficiency` 📈 | % | Self-sufficiency of the last completed cycle ([L3](03-self-sufficiency.md)) |
| `sensor.<p>_cycle_live_self_sufficiency` 💤 | % | Self-sufficiency of the in-progress cycle ([L3](03-self-sufficiency.md)) |
| `sensor.<p>_cycles_self_sufficiency_percentage_mean` 📈 | % | Energy-weighted self-sufficiency across all valid cycles ([L3](03-self-sufficiency.md)) |
| `sensor.<p>_cycle_completed_costovertime` 📈 | €/h | Cost per hour of the last completed cycle ([L2](02-cost.md)) |
| `sensor.<p>_cycles_costovertime_mean` 📈 | €/h | Average cost per running hour ([L2](02-cost.md)) |

**Inventory —** fully configured, with `[daily, monthly, yearly]`: **52 new entities** (173 cumulative) — 46 fixed plus 2 per period.

## Restarting mid-cycle

A cycle opens on `running` off→on and closes on on→off, which leaves an obvious question: what happens if Home Assistant restarts while an appliance is halfway through a run?

The cycle **survives**. Both boundary snapshots are restored across restarts, and a start newer than the last stop is exactly what "opened, not yet closed" means — so the tracker picks the run back up with its original start time and baselines. Since every cycle metric is a difference between the opening snapshot and the current lifetime value, the restart leaves no trace: duration and energy still span the whole run.

Two cases it deliberately does not try to rescue, because Home Assistant was not there to observe them:

- **The appliance finished while HA was down.** At restart there is nothing running, and the run is lost. There is no way to know when it stopped.
- **It stopped and started again while HA was down.** The two runs are folded into one, whose duration includes the gap — normally long enough for `max_duration` to reject it as `too_long`.

No cycle is ever invented: with no open start on record, the behaviour is the same as it would be without this recovery. Resumptions are logged at `INFO`.

## Events

When a cycle closes, one of two events fires on the Home Assistant bus — the intended hook for notifications and automations:

- `energy_profiler_cycle_completed` — the run passed the configured limits
- `energy_profiler_cycle_discarded` — it failed them (counters and means untouched)

Payload:

```yaml
device: washing_machine_em   # the device prefix
energy_kwh: 1.05             # energy delta of the cycle
duration_s: 5411.2           # duration in seconds
status: valid                # or too_short / too_long / too_little_energy / too_much_energy
cycle_count: 42              # valid cycles so far
```

## You are at the end of the path

173 entities on a fully-equipped device, and only a handful of database rows per day — provided the recorder is configured as described in [Recorder Setup](../recorder.md).

From here: the [entity reference](../entities.md) for looking anything up, [Configuration](../configuration.md) for every option in detail, and [Services & Actions](../services.md) for `reset` and the Lean maintenance services.

## Example

[`examples/full.yaml`](../../examples/full.yaml) — shared defaults and a mixed fleet across all levels.
