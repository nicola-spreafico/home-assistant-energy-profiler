# Level 2 — Cost

[← Level 1: Energy](01-energy.md) · [The levels](../../README.md#the-levels) · [Next: Self-sufficiency →](03-self-sufficiency.md)

> *"What did that device cost me this month — and what is it costing me right now?"*

Add one price sensor and every kWh gets priced **at the tariff valid at the moment it was consumed**. Past costs are never re-priced when the tariff changes, so a variable-rate contract stays accurate.

**Prerequisites:** [Level 1](01-energy.md).

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
| `sensor.<p>_energy_cost_instant_hourly` 💤 | €/h | Projected cost rate if the current draw held for an hour |
| `sensor.<p>_energy_cost_instant_daily` / `_monthly` / `_yearly` 💤 | €/d, €/m, €/y | The same projection over a day / 30-day month / year |

**Inventory —** with `[daily, monthly, yearly]`: **8 new entities** (13 cumulative).

```
sensor.<p>_energy_cost_lifetime
sensor.<p>_energy_cost_daily / _monthly / _yearly
sensor.<p>_energy_cost_instant_hourly / _daily / _monthly / _yearly
```

## Two kinds of cost, don't confuse them

- **`_energy_cost_*`** is *accumulated* — real money already spent, integrated delta by delta.
- **`_energy_cost_instant_*`** is a *projection* — "if the device kept drawing exactly this much, it would cost this per hour/day/month/year". It is an instantaneous rate for dashboards, never a total.

The instant projections read the raw power sensor, so they exist **only for the total group**: no gate applies to them, and they will not reappear in the running or standby groups at [Level 5](05-running.md) and [Level 6](06-standby.md).

## Composes with Level 3

Cost alone prices your total consumption. Add [Level 3](03-self-sufficiency.md) and the same price sensor also produces **savings** and **grid cost** — the monetary reading of the solar/grid split, which neither level unlocks on its own.

## Example

[`examples/basic_consumption.yaml`](../../examples/basic_consumption.yaml) — a single appliance with energy and cost.

## Next

Do you know what share of your consumption comes from your own production? → **[Level 3 — Self-sufficiency](03-self-sufficiency.md)**
