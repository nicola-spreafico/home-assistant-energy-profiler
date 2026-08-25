# Level 2 — Cost

[← Level 1: Energy](01-energy.md) · [The levels](../../README.md#the-levels) · [Next: Self-sufficiency →](03-self-sufficiency.md)

> *"What did that device cost me this month — and what is it costing me right now?"*

Add one price sensor and every kWh gets priced **at the tariff valid at the moment it was consumed**. Past costs are never re-priced when the tariff changes, so a variable-rate contract stays accurate.

**Prerequisites:** [Level 1](01-energy.md).

> **Home Assistant devices:** total costs and projections appear on **<name> · Energy**; enabled Running and Standby children receive the same cumulative cost sub-block.

## Minimum configuration

```yaml
energy_profiler:
  defaults:
    energy_price: sensor.energy_price_purchase   # €/kWh

  devices:
    - name: dishwasher
      power: sensor.dishwasher_power
      energy: sensor.dishwasher_energy
```

Declare `defaults:` **exactly once** for the whole system — it is the baseline every device inherits. Any device can override a key, or opt out entirely with `null`:

```yaml
    - name: dishwasher
      power: sensor.dishwasher_power
      energy: sensor.dishwasher_energy
      energy_price: null      # this device only: no cost tracking
```

## What you get

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_cost_lifetime` 💤 ↺ | € | Cost integrator: each energy delta priced at the tariff valid *at that moment* |
| `sensor.<p>_energy_cost_<period>` 🚫 | € | Lean period meters over the cost |
| `sensor.<p>_energy_cost_instant_<period>` 💤 | € / time | Projected cost rate if the current draw held: the **whole** draw at the import tariff, self-production ignored. One variant per `instant_periods:` (default: your `periods:`), each the €/h rate under a different multiplier |

**Inventory —** with `[daily, monthly, yearly]`: **7 new entities** (12 cumulative).

```
sensor.<p>_energy_cost_lifetime
sensor.<p>_energy_cost_daily / _monthly / _yearly
sensor.<p>_energy_cost_instant_daily / _monthly / _yearly
```

## Decimals shown

The accumulators integrate in `Decimal` and are **deliberately never rounded** — rounding each step would drift by whole cents over a lifetime of accumulation — so their raw state carries ~10 decimals. By default only 2 of them are *displayed*; [`cost_precision:`](../configuration.md#shared-defaults-defaults) changes that, globally or per device. It is a display setting: the stored state and the long-term statistics keep their full precision either way, and a precision you pick by hand on a single entity still overrides it.

Home Assistant has no built-in precision for the `monetary` device class — that is why the € entities need this, while the kWh ones get 2 decimals on their own from the `energy` device class.

## Two kinds of cost, don't confuse them

- **`_energy_cost_*`** is *accumulated* — real money already spent, integrated delta by delta.
- **`_energy_cost_instant_*`** is a *projection* — "if the device kept drawing exactly this much, it would cost this per hour/day/month/year". It is an instantaneous rate for dashboards, never a total.

The instant projections read the raw power sensor, so they exist **only for the total group**: no gate applies to them, and they will not reappear in the running or standby groups at [Level 5](05-running.md) and [Level 6](06-standby.md).

At this level they price the **entire** draw at the import tariff — they do not know about self-production yet, so an appliance running on solar still shows a cost. [Level 3](03-self-sufficiency.md) adds `_energy_cost_instant_from_grid_*`, the same projection re-based on the grid share, which answers what you are actually paying right now.

## Composes with Level 3

Cost alone prices your total consumption. Add [Level 3](03-self-sufficiency.md) and the same price sensor also produces **savings** and **grid cost** — the monetary reading of the solar/grid split, which neither level unlocks on its own.

## Example

[`examples/basic_consumption.yaml`](../../examples/basic_consumption.yaml) — a single appliance with energy and cost.

## Next

Do you know what share of your consumption comes from your own production? → **[Level 3 — Self-sufficiency](03-self-sufficiency.md)**
