# Level 8 — Prosumption: did production and consumption meet?

[← Level 7: Cycles](07-cycles.md) · [The levels](../../README.md#the-levels)

> *"You were 30% self-sufficient in January. Was that a bad month, or was that everything January could possibly have given you?"*

Levels 3 and 4 tell you where each appliance's energy **came from**. This level asks the opposite question — what happened to the energy you **produced** — and then uses the answer to do something the earlier levels cannot: rank your appliances by how well they actually used the sun, fairly, in a way that does not simply reward whichever one happens to run at midday by nature.

**Prerequisites:** none of the other levels, technically — this one reads energy counters rather than the instantaneous flows. In practice it pairs with [Level 3](03-self-sufficiency.md): the per-device half of this level needs the per-device split that Level 3 builds.

---

## Part 1 — One energy, two questions

### The identity everything rests on

Your house obeys one equation, always:

```
consumption = production + import − export
```

Rearrange it and something surprising falls out:

```
consumption − import  =  production − export
```

The left side is *"energy I consumed that I did not buy"*. The right side is *"energy I produced that I did not sell"*. **They are the same number.** Not approximately — identically, by the arithmetic of the meter. Call it `E_self`.

So there is only ever **one quantity** here. What changes is what you compare it against:

| Score | Formula | Asks |
| --- | --- | --- |
| **Self-sufficiency** | `E_self / consumption` | Did I cover my needs? |
| **Self-consumption** | `E_self / production` | Did my production find a use? |
| **Prosumption** | `E_self / min(consumption, production)` | Did the two meet in time? |

### Why two scores instead of one

Because each of the first two has a **ceiling it cannot pass**, and the ceiling is set by the *other* side.

**A January day.** You produce 6 kWh and consume 20 kWh. Even if you consumed every single watt-hour the panels made, self-sufficiency would read `6/20` = **30%**. There is no behaviour, no automation, no discipline that gets you past 30% that day. Reading 27% as a failure is reading the size of your roof, not the conduct of your house.

**A July day.** You produce 30 kWh and consume 12 kWh. Even if you consumed every watt-hour you could, self-consumption would read `12/30` = **40%**. The other 60% *has* to be exported: there is nothing left in the house that wants it. A low self-consumption in July is not waste, it is abundance.

So in every period one of the two scores is being dragged down by **plenty on its own side**, not by anything you did.

### What prosumption does about it

It divides by whichever side was actually scarce — the one that was really constraining you:

```
prosumption = E_self / min(consumption, production)
```

That is exactly the same as `max(self-sufficiency, self-consumption)`: the bigger ratio is by definition the one with the smaller denominator. Both forms are correct; the `min` form makes it obvious *why*.

The effect is that the sizing of **both** sides divides out, and what is left is only how well the two overlapped **in time**:

| | Production | Consumption | `E_self` | Self-suff. | Self-cons. | **Prosumption** |
| --- | --- | --- | --- | --- | --- | --- |
| January day | 6 kWh | 20 kWh | 5.4 | 27% | 90% | **90%** |
| July day | 30 kWh | 12 kWh | 9.0 | 75% | 30% | **75%** |

In January the ceiling was 30% and you reached 27% — so you captured 90% of what was physically available, and prosumption says so. In July the ceiling on self-consumption was 40% and you reached 30%; but prosumption reports 75%, because it measures against consumption, which was the scarce side that day.

The **complement of prosumption is the only real waste**: energy that existed, and demand that existed, which failed to meet because of the hour of the day. In July that is 25% — roughly 3 kWh you imported after sunset that a shifted load or a battery could have covered.

And it changes the question it asks with the season on its own: in winter it tracks self-consumption, in summer self-sufficiency. That is why it works as a single year-round number where neither of the other two does.

> **Terminology.** Self-sufficiency and self-consumption are the standard pair in the photovoltaic literature (often SSR and SCR), and their common numerator is the same `E_self` used here. Normalising by `min()` is what statistics calls an *overlap coefficient*. "Prosumption" is this integration's name for it.

---

## Part 2 — Minimum configuration

You declare **house energy counters, in kWh** — the totals your inverter or meter already publishes. Not power, not percentages, and not per-device anything.

```yaml
energy_profiler:
  defaults:
    energy_flows:
      consumption: sensor.house_consumption_energy_total   # required
      import:      sensor.grid_import_energy_total         # required
      production:  sensor.pv_production_energy_total       # optional
      export:      sensor.grid_export_energy_total         # optional
```

`energy_flows:` lives in `defaults:` only and has no per-device form. These are readings of the whole house; a device overriding them would be claiming a second house.

### What each counter unlocks

| You declare | You get |
| --- | --- |
| `consumption` + `import` | `E_self`, house self-sufficiency, and **the baseline** — which is what Part 3 needs |
| **+** `production` | self-consumption and **prosumption** |
| **+** `export` | the diagnostic cross-check only |

The graduation is not arbitrary. `consumption − import` already gives you `E_self`, so `export` adds no new information — its only job is to let the integration compute `E_self` *the other way* and compare. `production` is what genuinely unlocks the generation-side scores, because it is the only denominator that is not already known.

### What the counters must be

- **Monotonic totals**, not per-period sensors. The integration builds its own period meters from them, on your configured `periods:`. Feed it a daily-resetting sensor and every rollover looks like a meter reset.
- **`import` is import, `export` is export** — two separate counters, not one signed net figure. A single sensor that swings negative counts exports as negative imports and quietly corrupts `E_self`.
- **In kWh.** Counters in Wh will produce numbers 1000× off; the integration does not convert.

### The first period is warm-up — discard it

Nothing here reads your counters' absolute values. Each house quantity is accumulated from **deltas**, anchored at zero the moment the integration first sees the counter, because those counters were started on whatever day each meter was installed — on a real system the two readings of the same self-consumed energy sat 1574 kWh apart for that reason alone.

The consequence is that the period you switch this on in is **partial on the house side while the per-device meters already hold the whole period**. Enable it at 22:00 and the house has twenty minutes of night against a device that has run all day: the baseline is near zero, so `index` reads something absurd like 21× and `advantage` reads the device's entire self-fed energy.

Nothing is wrong and nothing needs fixing — from the next rollover both sides cover the same window. But the long-term point written for that first period is meaningless, and if you care about a clean series it is worth removing:

```yaml
action: lean_utility_meter.clear_history
target:
  entity_id: sensor.energy_profiler_self_sufficiency_percentage_daily
```

The same applies after a long outage, in proportion: the house accumulators skip whatever happened while Home Assistant was down, rather than dumping it into the period they restart in.

---

## Part 3 — The leaderboard

This is what the level is for. The goal is a table that answers *"which appliance is using my sun best?"* — and the obvious way to build it is wrong.

### Why ranking by percentage is unfair

Rank devices by `…_energy_from_self_percentage_daily` and two things go wrong, both flattering the wrong appliance.

**It ranks how schedulable a device is, not how well it was scheduled.** A fridge runs around the clock, so its self-sufficiency converges by construction on the house average. Not because it behaves badly — because it *cannot behave otherwise*. A washing machine can be moved, so its number reflects a decision. Put them in one column and you have ranked appliance categories.

**It ignores size.** A 5 W lamp on a sunny windowsill scores 100% and tops the table having moved 20 Wh. A heat pump at a modest 40% of 8 kWh moved 3.2 kWh off the grid — 160 times more.

**And it is not comparable across seasons.** 80% in January, when the house managed 20%, is an achievement. The same 80% in July, when the house managed 70%, is barely showing up.

### The two entities that fix it

Both compare a device against **the house over the same period**, so the weather is already divided out.

```
index_d      =  device self-sufficiency %  /  house self-sufficiency %      [×]

advantage_d  =  from_self_d  −  (energy_d × house self-sufficiency)         [kWh]
```

**`index`** is the readable one. `1.00` means the device drew its energy at moments statistically indistinguishable from the house as a whole — which is exactly where an unmovable load belongs: neither rewarded nor blamed. Above 1 it ran in the sun on purpose.

**`advantage`** is the rankable one. The subtracted term is what the device *would* have captured by drawing at the same times as the house; what is left is attributable to **when it ran**. It is in kWh, so the size of the appliance is already in the number.

### Worked example

A house day: consumption 20 kWh, `E_self` 6 kWh → **baseline 30%**.

| Device | Energy | `from_self` | `from_self %` | `index` | `advantage` |
| --- | --- | --- | --- | --- | --- |
| Dishwasher (ran at noon) | 1.5 kWh | 1.35 | 90% | **3.00×** | **+0.90 kWh** |
| Heat pump | 8.0 kWh | 3.20 | 40% | **1.33×** | **+0.80 kWh** |
| Bathroom lamp | 0.02 kWh | 0.02 | 100% | **3.33×** | **+0.014 kWh** |
| Fridge | 1.2 kWh | 0.36 | 30% | **1.00×** | **0.00 kWh** |
| Washing machine (ran at 3am) | 1.0 kWh | 0.05 | 5% | **0.17×** | **−0.25 kWh** |

Four things you can only see with both columns side by side:

- **The lamp has the best `index` in the house** and an `advantage` of nothing. Ranked by percentage or by index it wins; ranked by advantage it sits where it belongs.
- **The heat pump has a mediocre `index` and nearly the best `advantage`**, because it is big. 40% of 8 kWh moves far more sun than 90% of 1.5 kWh. This is the row to act on first.
- **The fridge lands on exactly 1.00× / 0.00 kWh.** That is the operational definition of an unmovable load, and it is neither punished nor praised.
- **The washing machine is the only negative number**, and it is the only genuine problem of the day.

### The zero-sum property

Add up those five advantages: **+1.464 kWh**. The rest of the house — 8.28 kWh of unprofiled load, of which 1.02 kWh was self-produced — comes to `1.02 − 8.28×0.30` = **−1.464 kWh**.

**Exactly zero.** This is algebraic, not luck: the baseline *is* the house's own energy-weighted mean, so deviations from it must cancel.

Two consequences. First, the leaderboard is a genuine **redistribution** — one appliance's surplus is another's deficit, which is what a ranking ought to be. Second, **the residual is a row worth reading**: it is published as `unprofiled_advantage_kwh` on the ranking entity, and a large negative one says your unmeasured baseline load runs at night. That is usually either the next thing to profile or the next thing to fix.

---

## What you get

**House scores** — on the system device (`sensor.energy_profiler_…`):

| Entity | Unit | Needs | Description |
| --- | --- | --- | --- |
| `energy_profiler_self_energy_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | — | `E_self`: consumption not imported, accumulated from signed deltas so a meter reset cannot leak in |
| `energy_profiler_consumption_<period>` 🚫 | kWh | — | House consumption per period — also the denominator of self-sufficiency |
| `energy_profiler_production_<period>` 🚫 | kWh | `production` | House production per period |
| `energy_profiler_self_sufficiency_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | — | `E_self / consumption`. **The baseline** every per-device comparison divides by |
| `energy_profiler_self_consumption_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | `production` | `E_self / production` |
| `energy_profiler_prosumption_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | `production` | `E_self / min(consumption, production)` — capped at 100 |
| `energy_profiler_energy_balance` 📈 | kWh | all four | Diagnostic: `(consumption − import) − (production − export)`, which must sit at ~0 |
| `energy_profiler_solar_ranking_<period>` 💤 | — | — | The leaderboard. State = leading device; attributes carry the ordered table |

**Per device** — only on the total energy group, and only where `energy_flows:` is declared:

| Entity | Unit | Description |
| --- | --- | --- |
| `<p>_energy_from_self_index_<period>` 🚫 | × | Device self-sufficiency ÷ house self-sufficiency, same period. 1.00 = indistinguishable from the house |
| `<p>_energy_from_self_advantage_<period>` 🚫 | kWh | Self-produced energy captured beyond what running at the house's own times would have given |

They are built on the total group only. *"Did the washing machine run in the sun"* is one question, and asking it again of its standby draw is not a second one.

### The ranking entity's attributes

```yaml
state: Dishwasher
attributes:
  cycle: daily
  ranking:
    - device: Dishwasher
      prefix: dishwasher_em
      advantage_kwh: 0.9
      index: 3.0
      from_self_percentage: 90.0
      energy_kwh: 1.5
    - device: Heat pump
      ...
  unprofiled_advantage_kwh: -1.464
  house_self_energy_kwh: 6.0
  house_consumption_kwh: 20.0
```

`unprofiled_advantage_kwh` is `null` when any profiled device is not reporting — a missing device would otherwise be silently folded into the remainder and misread as a fault of the unmeasured load.

---

## Two design decisions worth knowing about

These explain why the level is shaped the way it is, and why some things you might expect are absent.

### There is no instantaneous prosumption to persist

You can compute a live prosumption reading, and as a dashboard gauge it is fine. What you cannot do is **average it over a day and call that the day's figure** — it measures something else.

Take a day with two parts:

| | Duration | Power | Energy | Live self-share |
| --- | --- | --- | --- | --- |
| Night | 10 h | 200 W | 2 kWh | 0% |
| Midday | 2 h | 3000 W | 6 kWh | 100% |

- Time-average of the live score: `(10×0 + 2×100)/12` = **16.7%**
- Ratio of the energies: `6/8` = **75%**

The first weighs a 200 W moment as heavily as a 3 kW one. The relationship between them is exact:

```
energy ratio  =  time average  +  cov(power, self-share) / mean(power)
```

The correction term **is** the covariance between load and self-share — which is literally *"did you switch things on while the sun was up"*, the precise quantity this level exists to measure. Averaging live percentages does not merely blur it: it discards it, and discards more of it the better the house behaves.

There is a practical trap in this too. A live percentage published as a `measurement` sensor would have Home Assistant compute **hourly means** for it — that is, perform exactly the wrong aggregation, silently, and draw a plausible and systematically false graph.

So every score on this page is built from two *energy counters* of the same period, and each is metered so that one long-term point is written per period, holding the value at close. That point is the period's figure, not an average of readings taken during it.

### Production cannot be given to a device — and the reason is not "it's hard"

Level 3 attributes each appliance's *consumption* to grid or self, and it can do that because the appliance has its own meter: there is a measured quantity to apportion. Production has no such anchor. There is no washing-machine production meter, and there never will be.

You could try to hand each device a slice of the production in proportion to the self-production it absorbed — the only apportionment that is even defensible:

```
P_d = P × (self_d / E_self)
```

Then that device's self-consumption is:

```
self_d / P_d  =  self_d / (P × self_d / E_self)  =  E_self / P
```

`self_d` cancels. **Every appliance in the house scores exactly the same number**, the house figure. This is not a crude approximation worth making anyway — it is a quantity with zero information in it. That is why self-consumption and prosumption exist on the system device and nowhere else, and why the per-device half of this level is built out of the *baseline comparison* instead.

The same fact seen from another angle: the `min()` construct also collapses per device, since `min(consumption_d, production)` is always the device's consumption. Per-device prosumption would be a second copy of per-device self-sufficiency.

---

## Recorder

Everything on this page follows the usual classes ([Recorder Setup](../recorder.md)): the `_<period>` entities are Lean meters and must **not** be recorded; the `_lifetime` ones are live accumulators and are pure bloat.

Two additions specific to this level:

- **Hidden helper entities.** Each period score has a companion `…_<period>_live` sensor, registered but hidden in the UI. It exists so the period meter has a source to mirror, carries no state class, and writes no statistics. Exclude the `_live` glob from the recorder along with the rest.
- **The ranking entity carries a table in its attributes.** Attributes are recorded with the state, so leaving `sensor.energy_profiler_solar_ranking_*` recorded will store the whole leaderboard on every change. Exclude it; each device's own `_advantage_<period>` meter already holds the history that matters.

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.energy_profiler_*
  include:
    entities:
      - sensor.energy_profiler_energy_balance
```

---

## Inventory

With `periods: [daily, monthly, yearly]` and all four counters declared:

```
sensor.energy_profiler_self_energy_lifetime                  + _daily / _monthly / _yearly
sensor.energy_profiler_consumption_                            _daily / _monthly / _yearly
sensor.energy_profiler_production_                             _daily / _monthly / _yearly
sensor.energy_profiler_self_sufficiency_percentage_lifetime  + _daily / _monthly / _yearly
sensor.energy_profiler_self_consumption_percentage_lifetime  + _daily / _monthly / _yearly
sensor.energy_profiler_prosumption_percentage_lifetime       + _daily / _monthly / _yearly
sensor.energy_profiler_energy_balance
sensor.energy_profiler_solar_ranking_                          _daily / _monthly / _yearly

per device:
sensor.<p>_energy_from_self_index_                             _daily / _monthly / _yearly
sensor.<p>_energy_from_self_advantage_                         _daily / _monthly / _yearly
```

**29 house entities** (14 without `production`), plus **6 per profiled device**, plus one hidden `_live` helper behind each period score.

---

## Dashboard

The three house scores read best as gauges, and the leaderboard as a markdown card over the attributes:

```yaml
type: markdown
content: |
  {% set r = state_attr('sensor.energy_profiler_solar_ranking_daily', 'ranking') %}
  | Device | Advantage | Index |
  |---|---:|---:|
  {% for row in r -%}
  | {{ row.device }} | {{ row.advantage_kwh }} kWh | {{ row.index }}× |
  {% endfor -%}
  | *unprofiled* | {{ state_attr('sensor.energy_profiler_solar_ranking_daily', 'unprofiled_advantage_kwh') }} kWh | |
```

[← Level 7: Cycles](07-cycles.md) · [The levels](../../README.md#the-levels)
