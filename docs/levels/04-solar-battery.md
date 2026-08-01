# Level 4 — Solar vs battery

[← Level 3: Self-sufficiency](03-self-sufficiency.md) · [The levels](../../README.md#the-levels) · [Next: Running →](05-running.md)

> *"That washing-machine run was 90% self-sufficient — but was it sunshine, or did it drain the battery I needed for the evening?"*

A second-level split **inside** the self share: how much came straight from the panels versus out of the battery. Only meaningful if you store energy — without a battery, `from_self` is already all solar and this level adds nothing.

**Prerequisites:** [Level 3](03-self-sufficiency.md). This splits the `from_self` quantity, so it cannot exist without it.

## Minimum configuration

```yaml
energy_profiler:
  defaults:
    self_sufficiency_source: sensor.home_self_sufficiency      # from level 3
    solar_share_source: sensor.home_solar_share_of_self        # 0-100 %

  devices:
    - name: dishwasher
      power: sensor.dishwasher_power
      energy: sensor.dishwasher_energy
```

`solar_share_source` is the share **of the self-consumed energy** that came directly from the panels — the battery is the complement. Provide **exactly one** of `solar_share_source` or `battery_share_source`: they are two spellings of the same split, and the schema rejects both together. Whichever you give drives one side; the other side is computed as the exact remainder.

```yaml
template:
  - sensor:
      # % OF THE SELF share coming straight from the panels (complement = battery).
      - name: home_solar_share_of_self
        unit_of_measurement: "%"
        state_class: measurement
        availability: >
          {{ has_value('sensor.house_load_power') and has_value('sensor.grid_import_power')
             and has_value('sensor.battery_discharge_power') }}
        state: >
          {% set load = states('sensor.house_load_power') | float(0) %}
          {% set grid = states('sensor.grid_import_power') | float(0) %}
          {% set batt = states('sensor.battery_discharge_power') | float(0) %}
          {% set self = load - grid %}
          {% if self <= 0 %} 100
          {% else %} {{ ([ [ (self - batt) / self * 100, 0 ] | max, 100 ] | min) | round(1) }}
          {% endif %}
```

(The value rendered while `self <= 0` is irrelevant: the split only consumes the percentage when self energy is actually flowing.)

## What you get

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_power_from_solar` 💤 | W | Instantaneous watts coming straight from the panels (`power × ss% × share%`) |
| `sensor.<p>_power_from_battery` 💤 | W | The battery-discharge share — the complement inside self, so `from_solar + from_battery = from_self` |
| `sensor.<p>_energy_from_solar_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | Energy taken directly from the panels |
| `sensor.<p>_energy_from_battery_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | Energy taken from battery discharge — the exact remainder |

**Inventory —** with `[daily, monthly, yearly]`: **10 new entities** (47 cumulative).

```
sensor.<p>_power_from_solar / _power_from_battery
sensor.<p>_energy_from_solar_lifetime    + _daily / _monthly / _yearly
sensor.<p>_energy_from_battery_lifetime  + _daily / _monthly / _yearly
```

## How the two splits nest

```
total energy
├── from_grid                    ← level 3
└── from_self                    ← level 3
    ├── from_solar               ← level 4
    └── from_battery             ← level 4
```

Both levels are exact: `from_self + from_grid` = total, and `from_solar + from_battery` = `from_self`. There is no monetary view of this second split — savings and grid cost live at the `from_self`/`from_grid` boundary, since that is where money actually changes hands.

## Milestone: the block is complete

47 entities, and the measurement block is now everything this integration knows how to say about a slice of consumption. **Levels 5 to 7 do not add new kinds of sensor — they replicate this same block over differently-gated slices.** That is the whole mental model, and why a fully-equipped device reaches 177 entities.

## Next

Want to know how much of this happens while the appliance is actually working? → **[Level 5 — Running](05-running.md)**
