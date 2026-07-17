# Entities: base measurement — power, energy, source split, cost

[← Back to the entity catalog](entities.md) · [README](../README.md)

What **every** device gets from just `power:` + `energy:`, enriched by the optional sources (`energy_price`, `self_sufficiency_source`, `solar_share_source`/`battery_share_source`). `<p>` is the device prefix; `<period>` one entity per configured period. Markers (🚫/💤/📈/↺) are defined in the [catalog overview](entities.md).

## Power

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_power_max` 📈 ↺ | W | Running peak of the power sensor, kept across restarts until you reset it |
| `sensor.<p>_power_from_self` 💤 | W | Instantaneous share of the current draw covered by self-production (`power × pct`). Requires `self_sufficiency_source` |
| `sensor.<p>_power_from_grid` 💤 | W | Instantaneous share imported from the grid — the exact remainder, so the two always sum to the measured power |

## Total energy group (`<p>_energy`)

The ungated view: any consumption, whatever the device state. Its `_lifetime` is the **decoupled all-time total** (only positive deltas, so meter resets and plug swaps never zero it) that every other group and the cycle analytics read from.

| Entity | Unit | Requires | Description |
| --- | --- | --- | --- |
| `sensor.<p>_energy_lifetime` 💤 ↺ | kWh | — | The decoupled all-time accumulator — the source everything else reads from |
| `sensor.<p>_energy_<period>` 🚫 | kWh | — | Lean period meters: live counter in the UI, one consolidated LTS row per closed period |
| `sensor.<p>_energy_from_self_lifetime` 💤 ↺ | kWh | `self_sufficiency_source` | Share covered by self-production: each delta split by the current self-sufficiency % |
| `sensor.<p>_energy_from_grid_lifetime` 💤 ↺ | kWh | ” | Grid share — the exact remainder of the same atomic split, so `from_self + from_grid` = the total, always |
| `sensor.<p>_energy_from_self_<period>` / `_from_grid_<period>` 🚫 | kWh | ” | Lean period meters over the split |
| `sensor.<p>_energy_from_solar_lifetime` / `_from_battery_lifetime` 💤 ↺ (+ `_<period>` 🚫) | kWh | ” + a share source | Second-level split of the self share: direct solar vs battery discharge. `from_solar + from_battery = from_self`, always |
| `sensor.<p>_energy_cost_lifetime` 💤 ↺ | € | `energy_price` | Cost integrator: each delta priced at the tariff valid *at that moment* |
| `sensor.<p>_energy_cost_<period>` 🚫 | € | ” | Lean period meters over the cost |
| `sensor.<p>_energy_from_grid_savings_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | price + ss | What self-production saved (the `from_self` share priced) |
| `sensor.<p>_energy_from_grid_cost_lifetime` 💤 ↺ (+ `_<period>` 🚫) | € | price + ss | What the grid imports actually cost (`from_grid` priced) |
| `sensor.<p>_energy_self_sufficiency_lifetime` 💤 (+ `_<period>` 🚫) | % | `self_sufficiency_source` | Live ratio `from_self / total`; the period meters snapshot it as a gauge (one LTS point per period) |

**Instantaneous cost projections** (`power × price`, total group only):

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_energy_cost_instant_hourly` 💤 | €/h | Projected cost rate if the current draw held for an hour |
| `sensor.<p>_energy_cost_instant_daily` / `_monthly` / `_yearly` 💤 | €/d, €/m, €/y | Same projection over a day / 30-day month / year |

## Inventory

3 power + 9 lifetimes + 9 meters per period + 4 instant. Fully-configured, with `[daily, monthly, yearly]`: **43 entities**.

- `sensor.<p>_power_max`, `sensor.<p>_power_from_self`, `sensor.<p>_power_from_grid`
- `sensor.<p>_energy_lifetime` — and `sensor.<p>_energy_<period>`
- `sensor.<p>_energy_from_self_lifetime` — and `sensor.<p>_energy_from_self_<period>`
- `sensor.<p>_energy_from_grid_lifetime` — and `sensor.<p>_energy_from_grid_<period>`
- `sensor.<p>_energy_from_solar_lifetime` — and `sensor.<p>_energy_from_solar_<period>`
- `sensor.<p>_energy_from_battery_lifetime` — and `sensor.<p>_energy_from_battery_<period>`
- `sensor.<p>_energy_cost_lifetime` — and `sensor.<p>_energy_cost_<period>`
- `sensor.<p>_energy_from_grid_savings_lifetime` — and `sensor.<p>_energy_from_grid_savings_<period>`
- `sensor.<p>_energy_from_grid_cost_lifetime` — and `sensor.<p>_energy_from_grid_cost_<period>`
- `sensor.<p>_energy_self_sufficiency_lifetime` — and `sensor.<p>_energy_self_sufficiency_<period>`
- `sensor.<p>_energy_cost_instant_hourly` / `_daily` / `_monthly` / `_yearly`
