# Level 3 — Self-sufficiency: self vs grid

[← Level 2: Cost](02-cost.md) · [The levels](../../README.md#the-levels) · [Next: Solar vs battery →](04-solar-battery.md)

> *"Your house is 70% self-sufficient — but which device is dragging that number down?"*

This is the level the integration exists for. House-level dashboards tell you *what* your self-sufficiency is; this splits it **per device**, so you can see that the dishwasher already runs at 95% while the washing machine sits at 20% — and act where it pays.

**Prerequisites:** [Level 1](01-energy.md). Combines with [Level 2](02-cost.md) — see [Composition](#composition-with-level-2) below.

## Minimum configuration

```yaml
energy_profiler:
  defaults:
    self_sufficiency_source: sensor.home_self_sufficiency   # 0-100 %

  devices:
    - name: dishwasher
      power: sensor.dishwasher_power
      energy: sensor.dishwasher_energy
```

`self_sufficiency_source` is **any 0–100 sensor you provide**: the share of house consumption covered by local production. If your inverter integration does not expose it, derive it from the instantaneous power flows:

```yaml
template:
  - sensor:
      - name: home_self_sufficiency
        unit_of_measurement: "%"
        state_class: measurement
        availability: >
          {{ has_value('sensor.house_load_power') and has_value('sensor.grid_import_power') }}
        state: >
          {% set load = states('sensor.house_load_power') | float(0) %}
          {% set grid = states('sensor.grid_import_power') | float(0) %}
          {% if load <= 0 %} 0
          {% else %} {{ ([ [ (load - grid) / load * 100, 0 ] | max, 100 ] | min) | round(1) }}
          {% endif %}
```

(`(consumption − grid_import) / consumption`. Adapt the entity ids to your inverter.)

## What you get

**Instantaneous power split:**

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_power_from_self` 💤 | W | Share of the current draw covered by self-production (`power × pct`) |
| `sensor.<p>_power_from_grid` 💤 | W | Share imported from the grid — the exact remainder, so the two always sum to the measured power |

**Energy split and ratio:**

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_from_self_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | Energy covered by self-production: every delta split by the self-sufficiency % valid at that instant |
| `sensor.<p>_energy_from_grid_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | The grid share — the exact remainder of the same atomic split, so `from_self + from_grid` = the total, always |
| `sensor.<p>_energy_self_sufficiency_lifetime` 💤 (+ `_<period>` 🚫) | % | Live ratio `from_self / total`; the period meters snapshot it as a **gauge** (one long-term point per period, not a cumulative sum) |

**Unlocked together with [Level 2](02-cost.md)** — these need *both* a price and a self-sufficiency source:

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_from_grid_savings_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | What self-production saved you: the `from_self` share priced |
| `sensor.<p>_energy_from_grid_cost_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | What the grid imports actually cost: the `from_grid` share priced |

**Inventory —** with `[daily, monthly, yearly]` and a price already configured: **22 new entities** (35 cumulative). Without a price, 14 of them (the two monetary rows drop out).

```
sensor.<p>_power_from_self / _power_from_grid
sensor.<p>_energy_from_self_lifetime            + _daily / _monthly / _yearly
sensor.<p>_energy_from_grid_lifetime            + _daily / _monthly / _yearly
sensor.<p>_energy_self_sufficiency_lifetime     + _daily / _monthly / _yearly
sensor.<p>_energy_from_grid_savings_lifetime    + _daily / _monthly / _yearly   [needs price]
sensor.<p>_energy_from_grid_cost_lifetime       + _daily / _monthly / _yearly   [needs price]
```

## Composition with Level 2

This is the first place where levels **multiply instead of adding**. Cost alone gives you what a device spent; the split alone gives you where its energy came from. Together they answer the question neither can: *how much money did the sun save you, and how much did the grid actually charge you* — per device, per period.

## The split is exact by construction

One component owns the split and pushes the exact remainder to its partner, so `from_self + from_grid` equals the group total to the last decimal — no drift, no rounding gap. The same mechanism runs one level deeper at [Level 4](04-solar-battery.md), and identically inside every gated group at [Level 5](05-running.md) and [Level 6](06-standby.md).

## Example

[`examples/self_sufficiency.yaml`](../../examples/self_sufficiency.yaml) — the solar/grid split with savings and grid cost.

## Next

Do you have a battery, and want to know how much came straight from the panels? → **[Level 4 — Solar vs battery](04-solar-battery.md)**
