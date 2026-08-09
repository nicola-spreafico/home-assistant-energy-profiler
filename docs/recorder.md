# Recorder Setup

[← Back to README](../README.md)

This integration creates many entities per device, and they are **not all equal** from the recorder's point of view. Getting this section right is what keeps your database small — and, for the period meters, it is a **correctness requirement**, not an optimization.

## First, the reassurance

Over two hundred entities per device sounds like a database catastrophe. It is not, and the arithmetic is worth seeing before the rules below, because it explains why the rules are shaped the way they are.

A period meter writes **one long-term row per closed period** and — excluded from the recorder as documented here — **no state rows at all**. An ordinary utility meter writes one long-term row per *hour*, plus a state row every time its source moves.

Measured on a real fully-equipped device with `[daily, monthly, yearly]`:

| | Long-term rows / year | State rows / year |
| --- | ---: | ---: |
| **90 period meters** — an entire device | ~11,300 | **0** |
| **One ordinary utility meter**, recorded | 8,760 | 100,000+ |

An entire device's ninety meters cost roughly what **one** conventional meter costs in statistics, and nothing at all in state rows. The entity count measures how many questions you can ask; it does not measure what is being written down.

None of that is automatic, though — it is exactly what the rest of this page buys you. Record the period meters by mistake and you get the worst of both: duplicated statistics on two different baselines, and corrupted graphs.

## The three classes of entities

**1. Period meters — must NOT be recorded.**
Every per-period meter (`…_energy_daily`, `…_energy_cost_monthly`, `…_cycles_count_yearly` — a period suffix `_hourly`, `_daily`, `_weekly`, `_monthly`, `_bimonthly`, `_quarterly` or `_yearly` in the **`lifetime` slot**, i.e. where the entity would otherwise end in `_lifetime`) is backed by the Lean core and **writes its own long-term statistics** — one consolidated row per period. If the recorder also records these entities, Home Assistant compiles its own hourly statistics *into the same series*: you get duplicate rows on two different baselines, and the graphs show impossible jumps. This is not hypothetical — see [What happens if you get it wrong](#what-happens-if-you-get-it-wrong).

> **The one exception to "ends in a period suffix".** The instantaneous cost projections — `…_energy_cost_instant_<period>` and `…_cost_instant_from_grid_<period>` — end in the same words but are **not** period meters: they are live projections of the current draw, and belong to class 2 below. There the period names a *rate* (€ per day), not an accumulation window. Excluding them is right; treating them as Lean meters is not.

**2. Live/accumulator entities — recording is pure bloat.**
The `…_lifetime` accumulators, the instantaneous projections (`…_energy_cost_instant_*`), the in-progress cycle views (`…_cycle_live_*`), the power split (`…_power_from_self/grid`) and `…_standby_duration` update very frequently (some on every power tick). They survive restarts through Home Assistant's state restore mechanism, so the recorder adds nothing but thousands of rows per day. Exclude them.

**3. Discrete analytics — worth recording.**
A short list of entities changes only at meaningful moments (a cycle closes) and their **state history** is genuinely useful:

| Entity | Why record it |
| --- | --- |
| `sensor.<prefix>_cycle_completed_*` | one value per valid cycle — the per-run history of energy/cost/duration/… |
| `sensor.<prefix>_cycles_*_mean` | slow-moving averages, nice to graph over time |
| `sensor.<prefix>_cycle_validation_status` | audit trail of accepted/discarded cycles |
| `sensor.<prefix>_power_max` | peak power history |
| `binary_sensor.<prefix>_running` | when the appliance actually ran |

## Which situation are you in?

Home Assistant's recorder records **everything by default**. Which recipe applies depends on whether your `recorder:` config already uses `include`:

- no `recorder:` filter at all, or only `exclude:` → you are **exclude-based** (the default)
- your `recorder:` has `include:` and relies on it to whitelist entities → you are **include-based**

### Exclude-based systems (Home Assistant default)

Exclude everything of the device with one glob per domain, then re-admit the useful entities by listing them **explicitly under `include.entities`** (an explicit entity include always wins over an exclude glob; and as long as `include` contains only `entities` — no domains, no globs — the rest of your system keeps being recorded as before):

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.washing_machine_em_*
      - binary_sensor.washing_machine_em_*
  include:
    entities:
      - sensor.washing_machine_em_cycle_completed_energy
      - sensor.washing_machine_em_cycle_completed_cost
      - sensor.washing_machine_em_cycle_completed_duration
      - sensor.washing_machine_em_cycles_energy_mean
      - sensor.washing_machine_em_cycles_cost_mean
      - sensor.washing_machine_em_cycles_duration_mean
      - sensor.washing_machine_em_cycle_validation_status
      - sensor.washing_machine_em_power_max
      - binary_sensor.washing_machine_em_running
```

`washing_machine_em` is the device `name` plus the configured `name_suffix` — adjust to your prefix, and repeat per device (packages merge `recorder:` blocks natively, so each device's package can carry its own block).

### Include-based (whitelist) systems

If your recorder already works as a whitelist, simply add the useful entities to the include list — everything else, period meters included, stays out with no extra work:

```yaml
recorder:
  include:
    entity_globs:
      - sensor.washing_machine_em_cycle_completed_*
      - sensor.washing_machine_em_cycles_*_mean
    entities:
      - sensor.washing_machine_em_cycle_validation_status
      - sensor.washing_machine_em_power_max
      - binary_sensor.washing_machine_em_running
```

> ⚠️ **Do not include broadly and carve out with exclude.** It is tempting to write `include: entity_globs: [sensor.washing_machine_em_*]` plus an `exclude:` for the meters. It does not work: in Home Assistant's recorder filter, **a match on an include glob wins over the exclude glob**, so the period meters end up recorded anyway. Include narrowly instead, as shown above.

## The system device

The house entities ([Level 8](levels/08-prosumption.md)) follow the same three classes, with two things worth calling out:

- **The hidden `…_<period>_live` helpers.** Each house and baseline score has one. It exists purely to give its period meter a source to mirror, carries no state class and writes no statistics — but the recorder still stores its *states* unless excluded, and it changes as often as the meters it reads.
- **`sensor.energy_profiler_solar_ranking_<period>` carries the whole leaderboard in its attributes**, and attributes are stored with every state change. Exclude it: each device's own `…_from_self_advantage_<period>` meter already holds the history that matters.

One glob covers the lot, with the diagnostic readmitted explicitly:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.energy_profiler_*
  include:
    entities:
      - sensor.energy_profiler_energy_balance   # 📈 the meters-disagree check
```

## Self-check: Repairs

You don't have to take it on faith. Shortly after startup, the Lean core checks every period meter against the *actual* recorder filter and raises a **Repair** (Settings → Repairs, `recorder_not_excluded_<entity_id>`) for each meter the recorder would record. A clean setup shows none of them. One warning per meter of a freshly-added device is the typical symptom of a missing or wrong recorder block.

## What happens if you get it wrong

Nothing crashes — which is exactly the problem. The recorder silently compiles hourly statistics into the same long-term series the Lean meters maintain, on a different cumulative baseline. Days later, the energy graphs show duplicated or negative bars.

Recovery is supported but explicit: fix the recorder config, restart, then run `lean_utility_meter.thin_history` on each affected meter (the period meters are native Lean entities) — it rebuilds the series keeping only the consolidated per-period rows (and clears the accumulated short-term statistics and state rows too). Take a database backup first; the operation deletes data by design.
