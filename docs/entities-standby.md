# Entities: standby — the gatekeeper and the standby-energy group

[← Back to the entity catalog](entities.md) · [README](../README.md)

What the `standby:` option adds: the standby **gatekeeper** and the "vampire" energy drawn **while the device is idle**. `<p>` is the device prefix; markers (🚫/💤/📈/↺) are defined in the [catalog overview](entities.md).

## The gatekeeper

| Entity | Unit | Description |
| --- | --- | --- |
| `binary_sensor.<p>_standby` 📈 | — | `on` while the device is in standby, per the configured flavor (`true` = running off; power range with inverted thresholds; template — see [configuration](configuration.md#standby-standby)). In the default flavor it mirrors `…_running` inverted, so recording both is redundant |

## Standby energy group (`<p>_standby_energy`)

The **same block as the [total group](entities-base.md#total-energy-group-p_energy)** — energy, self/grid split, solar/battery split, cost, savings/grid-cost, self-sufficiency %, each as lifetime + period meters — accumulated **only while `…_standby` is on**. Sourced from the decoupled total lifetime; while the gatekeeper is off *or unavailable* the baseline advances without accumulating, so active-cycle (or unknown) energy is never counted as standby.

The solar/battery and self/grid splits answer questions like "how much of my standby waste was actually paid grid energy?" — typically most of it, since standby is largely nocturnal.

**Extra, this group only:**

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_standby_duration` 💤 | s | How long the current standby stretch has lasted (0 while not in standby) |

## Inventory

9 lifetimes + 9 meters per period (+ the gatekeeper and the duration). Fully-configured, with `[daily, monthly, yearly]`: **38 entities**.

- `binary_sensor.<p>_standby`
- `sensor.<p>_standby_duration`
- `sensor.<p>_standby_energy_lifetime` — and `sensor.<p>_standby_energy_<period>`
- `sensor.<p>_standby_energy_from_self_lifetime` — and `sensor.<p>_standby_energy_from_self_<period>`
- `sensor.<p>_standby_energy_from_grid_lifetime` — and `sensor.<p>_standby_energy_from_grid_<period>`
- `sensor.<p>_standby_energy_from_solar_lifetime` — and `sensor.<p>_standby_energy_from_solar_<period>`
- `sensor.<p>_standby_energy_from_battery_lifetime` — and `sensor.<p>_standby_energy_from_battery_<period>`
- `sensor.<p>_standby_energy_cost_lifetime` — and `sensor.<p>_standby_energy_cost_<period>`
- `sensor.<p>_standby_energy_from_grid_savings_lifetime` — and `sensor.<p>_standby_energy_from_grid_savings_<period>`
- `sensor.<p>_standby_energy_from_grid_cost_lifetime` — and `sensor.<p>_standby_energy_from_grid_cost_<period>`
- `sensor.<p>_standby_energy_self_sufficiency_lifetime` — and `sensor.<p>_standby_energy_self_sufficiency_<period>`
