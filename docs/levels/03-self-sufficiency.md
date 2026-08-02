# Level 3 — Self-sufficiency: self vs grid

[← Level 2: Cost](02-cost.md) · [The levels](../../README.md#the-levels) · [Next: Solar vs battery →](04-solar-battery.md)

> *"Your house is 70% self-sufficient — but which device is dragging that number down?"*

This is the level the integration exists for. House-level dashboards tell you *what* your self-sufficiency is; this splits it **per device**, so you can see that the dishwasher already runs at 95% while the washing machine sits at 20% — and act where it pays.

**Prerequisites:** [Level 1](01-energy.md). Combines with [Level 2](02-cost.md) — see [Composition](#composition-with-level-2) below.

## Minimum configuration

You give the integration the **house power flows**, in W — the readings your inverter or energy meter already publishes. No percentages, no templates: the shares are computed here.

```yaml
energy_profiler:
  defaults:
    power_flows:
      load: sensor.house_load_power     # total house consumption
      grid: sensor.grid_import_power    # the part covered by the grid
      # solar / battery: not needed at this level — see Level 4

  devices:
    - name: dishwasher
      power: sensor.dishwasher_power
      energy: sensor.dishwasher_energy
```

Everything the load draws that the grid is not covering is self-production, so these two sensors are all Level 3 needs. Add a `battery:` flow and you also get [Level 4](04-solar-battery.md).

### What the flows must mean

Each flow is a **contribution to the house load**, and the ones you declare must add up to it. Two consequences worth internalising before you pick entities:

- `grid` is import, not net exchange. A sensor that goes negative while exporting is fine — negatives are clamped to zero — but one that reports import minus export as a single signed number is not: while you export it reads negative and the split silently sees zero grid.
- `solar`, if you declare it, is the part of the panels' output that reaches the **load** — never the raw production. Production also feeds the battery and the export, so using it inflates the solar share exactly when production is highest. This is why `load:` exists: with `load` + `grid` (+ `battery`), the solar contribution is derived as the remainder and cannot be wrong in that way.

Declaring both `load` and `solar` is rejected by the schema rather than silently resolved, since a wrong choice there skews every device with no visible symptom.

## What you get

**Instantaneous power split:**

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_power_from_self` 💤 | W | Share of the current draw covered by self-production |
| `sensor.<p>_power_from_grid` 💤 | W | Share imported from the grid — the exact complement, so the two always sum to the measured power |

**Energy split and ratios:**

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_from_self_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | Energy covered by self-production: every delta split by the flows valid at that instant |
| `sensor.<p>_energy_from_grid_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | The grid share — the exact remainder of the same atomic split, so `from_self + from_grid` = the total, always |
| `sensor.<p>_energy_from_self_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | Live ratio `from_self / total`; the period meters snapshot it as a **gauge** (one long-term point per period, not a cumulative sum) |
| `sensor.<p>_energy_from_grid_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | The grid's share of the total — the complement of self-sufficiency, kept as its own entity so a three-slice breakdown needs no template |

**Unlocked together with [Level 2](02-cost.md)** — these need *both* a price and the flows:

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_from_grid_savings_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | What self-production saved you: the `from_self` share priced |
| `sensor.<p>_energy_from_grid_cost_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | What the grid imports actually cost: the `from_grid` share priced |
| `sensor.<p>_energy_cost_instant_from_grid_<period>` 💤 | € / time | The [Level 2](02-cost.md) projection re-based on `power_from_grid`: what the current draw is *actually* costing you, self-production netted off. Runs entirely on solar → 0 |

**Inventory —** with `[daily, monthly, yearly]` and a price already configured: **29 new entities** (41 cumulative). Without a price, 11 of them drop out (the two monetary rows and the three `_cost_instant_from_grid_*` projections).

```
sensor.<p>_power_from_self / _power_from_grid
sensor.<p>_energy_from_self_lifetime              + _daily / _monthly / _yearly
sensor.<p>_energy_from_grid_lifetime              + _daily / _monthly / _yearly
sensor.<p>_energy_from_self_percentage_lifetime   + _daily / _monthly / _yearly
sensor.<p>_energy_from_grid_percentage_lifetime   + _daily / _monthly / _yearly
sensor.<p>_energy_from_grid_savings_lifetime      + _daily / _monthly / _yearly   [needs price]
sensor.<p>_energy_from_grid_cost_lifetime         + _daily / _monthly / _yearly   [needs price]
```

## Composition with Level 2

This is the first place where levels **multiply instead of adding**. Cost alone gives you what a device spent; the split alone gives you where its energy came from. Together they answer the question neither can: *how much money did the sun save you, and how much did the grid actually charge you* — per device, per period.

## The split is exact by construction

One component owns the split: on each energy tick it reads the flows once, computes the self portion, and derives the grid portion as the **remainder** rather than as a second independent product. `from_self + from_grid` therefore equals the group total to the last decimal — no drift, no rounding gap — and the same holds one level down at [Level 4](04-solar-battery.md) and inside every gated group at [Level 5](05-running.md) and [Level 6](06-standby.md).

If the flows are unreadable, the tick is attributed entirely to the grid. A broken sensor can understate your self-production; it can never inflate it, nor the savings computed from it.

## This is attribution, not measurement

No one can know which electron reached the dishwasher. What happens here is that each device is assumed to draw from the house mix in the same proportions the house is drawing at that instant.

That assumption is exact when the declared flows really are contributions to the load, and it degrades gracefully when they are approximations. It is the same assumption any per-device solar figure rests on — here it simply lives in the code, where it can be documented and checked, instead of inside a template you had to write.

## Percentages are outputs, never inputs

Nothing in this level asks you for a percentage. Every percentage entity is a ratio of two accumulators, which means a closed period meter reads the **energy-weighted** share of that period.

That distinction matters more than it looks. Averaging instantaneous percentages over a day would tell you something quite different: a dishwasher drawing 2 kWh at noon on pure sun and 0.05 kWh overnight from the grid averages to roughly 50%, while the honest answer — the share of its energy that was sun — is 97.6%. Only the ratio of the meters answers the question you actually asked.

## Example

[`examples/self_sufficiency.yaml`](../../examples/self_sufficiency.yaml) — the solar/grid split with savings and grid cost.

## Next

Do you have a battery, and want to know how much came straight from the panels? → **[Level 4 — Solar vs battery](04-solar-battery.md)**
