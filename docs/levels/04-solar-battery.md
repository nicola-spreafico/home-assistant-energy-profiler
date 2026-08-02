# Level 4 — Solar vs battery

[← Level 3: Self-sufficiency](03-self-sufficiency.md) · [The levels](../../README.md#the-levels) · [Next: Running →](05-running.md)

> *"That washing-machine run was 90% self-sufficient — but was it sunshine, or did it drain the battery I needed for the evening?"*

Naming the self share. Level 3 tells you how much energy did not come from the grid; this level tells you what it was made of.

**Prerequisites:** [Level 3](03-self-sufficiency.md). It qualifies the same self share, so it cannot exist without it.

## Minimum configuration

One more flow: the battery.

```yaml
energy_profiler:
  defaults:
    power_flows:
      load: sensor.house_load_power
      grid: sensor.grid_import_power
      battery: sensor.battery_discharge_power   # discharge only, never charge
      # solar: — derived as load − grid − battery. Declare it instead of `load:`
      # only if your inverter exposes solar-to-load (not raw production).

  devices:
    - name: dishwasher
      power: sensor.dishwasher_power
      energy: sensor.dishwasher_energy
```

The solar contribution is whatever the load is not drawing from the grid or the battery, computed from the same three readings at the same instant. If your inverter *does* expose solar-to-load directly, declare `solar:` instead of `load:` — never both.

`battery` must be **discharge power**. A signed battery sensor that goes negative while charging works (negatives are clamped to zero); one that reports charging as a positive number does not, and would be counted as if it were feeding the house.

## The channels you declare are the channels you get

The flow block decides which entities exist, and nothing is created that would only ever read zero:

| Declared | Channels | `from_self` equals |
| --- | --- | --- |
| `load` + `grid` | — | the unqualified self share ([Level 3](03-self-sufficiency.md) only) |
| `load` + `grid` + `battery` | solar, battery | `from_solar + from_battery` |
| `grid` + `solar` | solar | `from_solar` |
| `grid` + `battery` | battery | `from_battery` |
| `grid` + `solar` + `battery` | solar, battery | `from_solar + from_battery` |

With a single channel, `from_self` and that channel carry the same number. Both still exist: `from_self` is what the monetary view prices and what analytics ask for when the source does not matter, while the channel entity is the one named for what actually happened. What is *not* duplicated is the percentage — with one channel it would be a second copy of self-sufficiency, so it is not created.

### Two channels, named after the common case

The channels are `solar` and `battery`, matching the vocabulary of Home Assistant's own Energy Dashboard, which likewise has a solar section and a battery section and no generic "generation" concept.

If your local production is **wind** rather than photovoltaic, declare it as `solar`: the arithmetic is identical — it is whatever local production reaches the load — and only the entity name reads oddly. The same applies in the Energy Dashboard, so at least the two are consistent.

A fuel-burning **generator is a different matter, and does not belong here**. The monetary view assumes self-production is free: `from_grid_savings` prices the self share at your grid tariff and calls it a saving, meaning "what you would have paid had this come from the grid". Energy from a generator was paid for — in fuel instead of on the bill — so that figure would be overstated, and the real saving is the difference between two costs, which this integration does not model. Sun and wind cost nothing at the margin and fit; a generator does not.

## What you get

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_power_from_solar` 💤 | W | Instantaneous watts coming straight from the panels |
| `sensor.<p>_power_from_battery` 💤 | W | The battery-discharge share, so `from_solar + from_battery = from_self` |
| `sensor.<p>_energy_from_solar_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | Energy taken directly from the panels |
| `sensor.<p>_energy_from_battery_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | Energy taken from battery discharge — the exact remainder |
| `sensor.<p>_energy_from_solar_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | Solar share **of the device total**, as a gauge |
| `sensor.<p>_energy_from_battery_percentage_lifetime` 💤 (+ `_<period>` 🚫) | % | Battery share of the device total |

**Inventory —** with `[daily, monthly, yearly]` and both channels: **18 new entities** (59 cumulative).

```
sensor.<p>_power_from_solar / _power_from_battery
sensor.<p>_energy_from_solar_lifetime               + _daily / _monthly / _yearly
sensor.<p>_energy_from_battery_lifetime             + _daily / _monthly / _yearly
sensor.<p>_energy_from_solar_percentage_lifetime    + _daily / _monthly / _yearly
sensor.<p>_energy_from_battery_percentage_lifetime  + _daily / _monthly / _yearly
```

## How the quantities nest

```
total energy
├── from_grid                    ← level 3
└── from_self                    ← level 3
    ├── from_solar               ← level 4
    └── from_battery             ← level 4
```

Both boundaries are exact: `from_self + from_grid` = the total, and `from_solar + from_battery` = `from_self`. Each is guaranteed the same way — one side is computed, the other is the remainder — and all of it happens in a single callback from a single reading of the flows, so the two boundaries can never disagree about the same tick.

The **percentages**, by contrast, are all taken against the device total: `from_grid_percentage`, `from_solar_percentage` and `from_battery_percentage` sum to 100, and self-sufficiency is `from_solar_percentage + from_battery_percentage`. There is no "percentage of self" entity — that quantity only ever existed as a configuration input, and there are no configuration inputs left that are percentages.

There is no monetary view of this split. Savings and grid cost live at the `from_self` / `from_grid` boundary, since that is where money actually changes hands — sun and battery both cost zero, and splitting savings between them would be two entities saying one thing.

## Milestone: the block is complete

59 entities, and the measurement block is now everything this integration knows how to say about a slice of consumption. **Levels 5 to 7 do not add new kinds of sensor — they replicate this same block over differently-gated slices.** That is the whole mental model, and why a fully-equipped device reaches its final count.

## Next

Want to know how much of this happens while the appliance is actually working? → **[Level 5 — Running](05-running.md)**
