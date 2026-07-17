# Entities: running — the signal and the running-energy group

[← Back to the entity catalog](entities.md) · [README](../README.md)

What the `running:` block adds: the detection **signal** and the energy consumed **while the device is on** — regardless of whether cycles are tracked. `<p>` is the device prefix; markers (🚫/💤/📈/↺) are defined in the [catalog overview](entities.md).

## The signal

| Entity | Unit | Description |
| --- | --- | --- |
| `binary_sensor.<p>_running` 📈 | — | `on` while the appliance runs, according to the configured power threshold (with `for:`-style debounce) or template trigger. Everything running-related hangs on it: this group, [cycle tracking](entities-cycles.md) and the default flavor of [standby](entities-standby.md) |

## Running energy group (`<p>_running_energy`)

The **same block as the [total group](entities-base.md#total-energy-group-p_energy)** — energy, self/grid split, solar/battery split, cost, savings/grid-cost, self-sufficiency %, each as lifetime + period meters — accumulated **only while `…_running` is on**. Sourced from the decoupled total lifetime, so it inherits the reset/plug-swap protection; while the signal is off *or unavailable* the baseline advances without accumulating, so uncertain periods are never counted.

Two things it is *not*:

- it is **not** the cycles family: `…_cycles_energy_lifetime` counts only *validated* runs, this group counts **every** running moment, limits or no limits — it is what lets you split running vs standby consumption without tracking cycles;
- it is **not** guaranteed to complement standby exactly: each group is gated independently (`total ≈ running + standby + residual`, no enforced identity).

Entity meanings are identical to the [total group's table](entities-base.md#total-energy-group-p_energy) with base `<p>_running_energy`; the only differences are the gate and the absence of the instant projections.

## Inventory

9 lifetimes + 9 meters per period (+ the signal). Fully-configured, with `[daily, monthly, yearly]`: **37 entities**.

- `binary_sensor.<p>_running`
- `sensor.<p>_running_energy_lifetime` — and `sensor.<p>_running_energy_<period>`
- `sensor.<p>_running_energy_from_self_lifetime` — and `sensor.<p>_running_energy_from_self_<period>`
- `sensor.<p>_running_energy_from_grid_lifetime` — and `sensor.<p>_running_energy_from_grid_<period>`
- `sensor.<p>_running_energy_from_solar_lifetime` — and `sensor.<p>_running_energy_from_solar_<period>`
- `sensor.<p>_running_energy_from_battery_lifetime` — and `sensor.<p>_running_energy_from_battery_<period>`
- `sensor.<p>_running_energy_cost_lifetime` — and `sensor.<p>_running_energy_cost_<period>`
- `sensor.<p>_running_energy_from_grid_savings_lifetime` — and `sensor.<p>_running_energy_from_grid_savings_<period>`
- `sensor.<p>_running_energy_from_grid_cost_lifetime` — and `sensor.<p>_running_energy_from_grid_cost_<period>`
- `sensor.<p>_running_energy_self_sufficiency_lifetime` — and `sensor.<p>_running_energy_self_sufficiency_<period>`
