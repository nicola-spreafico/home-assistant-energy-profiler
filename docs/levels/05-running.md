# Level 5 — Running

[← Level 4: Solar vs battery](04-solar-battery.md) · [The levels](../../README.md#the-levels) · [Next: Standby →](06-standby.md)

> *"Of everything this device consumed, how much was it actually doing something?"*

The first level on the **other axis**. Levels 1–4 asked *what you can measure*; from here on the question is *which slice of the consumption you measure it over*. Teach the integration to tell "on" from "off", and it replicates the entire block you built so far over the running slice alone.

**Prerequisites:** [Level 1](01-energy.md). Whatever you configured in levels 2–4 is inherited automatically.

## Minimum configuration

Two detection flavors. **Power threshold**, with debounce:

```yaml
energy_profiler:
  devices:
    - name: washing_machine
      power: sensor.washing_machine_power
      energy: sensor.washing_machine_energy
      running:
        trigger: power
        on_above: 5                # W, running above this…
        on_delay: "00:00:30"       # …held for 30 s
        off_below: 2               # W, stopped below this…
        off_delay: "00:02:00"      # …held for 2 min (rides out mid-cycle pauses)
```

Or **template**, when another entity already knows:

```yaml
      running:
        trigger: template
        available: "{{ has_value('climate.bedroom_ac') }}"
        state: "{{ states('climate.bedroom_ac') != 'off' }}"
```

Set `off_delay` generously for appliances that pause mid-programme (washing machines idle between fill and spin): without it, one run is recorded as several.

## What you get

**The signal:**

| Entity | Unit | Description |
| --- | --- | --- |
| `binary_sensor.<p>_running` 📈 | — | `on` while the appliance runs. Everything running-related hangs on it: this group, [cycle tracking](07-cycles.md) and the default flavor of [standby](06-standby.md) |
| `sensor.<p>_status` 📈 | enum | Presentation-only dashboard label. With running alone: `running` / `poweroff`. Gains `standby` at [Level 6](06-standby.md) |

**The running energy group (`<p>_running_energy`):** exactly the block from levels 1–4, accumulated **only while the signal is on**.

Every id below exists twice: as `_lifetime` 💤 ↺ (shown) and as one `_<period>` 🚫 meter per configured period — e.g. `sensor.<p>_running_energy_from_self_lifetime` plus `…_from_self_daily` / `_monthly` / `_yearly`.

| Entity | Requires | Description |
| --- | --- | --- |
| `sensor.<p>_running_energy_lifetime` | — | Energy consumed while running |
| `sensor.<p>_running_energy_from_self_lifetime` / `…_from_grid_lifetime` | [L3](03-self-sufficiency.md) | Solar/grid split of the running consumption |
| `sensor.<p>_running_energy_from_solar_lifetime` / `…_from_battery_lifetime` | [L4](04-solar-battery.md) | Solar/battery split inside the self share |
| `sensor.<p>_running_energy_cost_lifetime` | [L2](02-cost.md) | What the running consumption cost |
| `sensor.<p>_running_energy_from_grid_savings_lifetime` / `…_from_grid_cost_lifetime` | [L2](02-cost.md) + [L3](03-self-sufficiency.md) | Savings and grid cost of the running slice |
| `sensor.<p>_running_energy_self_sufficiency_lifetime` | [L3](03-self-sufficiency.md) | Self-sufficiency % while running (period meters are gauges) |

Same shape as the total group. The only thing that does **not** reappear here is `_energy_cost_instant_*`: those read raw power, which no gate applies to.

**Inventory —** fully configured, with `[daily, monthly, yearly]`: **38 new entities** (83 cumulative) — the signal, the status label, and 36 for the group.

## Gating is safe by construction

The group sources the **decoupled total lifetime** from [Level 1](01-energy.md), so it inherits the same reset/plug-swap protection. While the signal is off *or unavailable*, the baseline advances without accumulating: an uncertain period is never counted as running consumption rather than being guessed at.

## Running is not cycles

This group counts **every running moment**, whether or not that run was a plausible one. [Level 7](07-cycles.md) counts only *validated* runs. A discarded run still shows up here — which is exactly what lets you split running from standby consumption without tracking cycles at all.

Note the accounting: `total ≈ running + standby + off-residual` only when both gates exist and never overlap. Each group is gated independently; there is no enforced identity.

## Example

[`examples/cycle_counting.yaml`](../../examples/cycle_counting.yaml) — running detection in both flavors.

## Next

Curious how much the device burns doing nothing? → **[Level 6 — Standby](06-standby.md)**
