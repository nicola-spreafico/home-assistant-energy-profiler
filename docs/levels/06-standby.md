# Level 6 — Standby

[← Level 5: Running](05-running.md) · [The levels](../../README.md#the-levels) · [Next: Cycles →](07-cycles.md)

> *"How much money does the TV burn per year just sitting there — and was any of it even solar?"*

The vampire slice. Same block again, gated on "the device is idle but still drawing". Because standby is largely nocturnal, its solar/grid split usually reveals that nearly all of it is paid grid energy.

**Prerequisites:** [Level 1](01-energy.md). The default flavor also needs [Level 5](05-running.md); the standalone flavors do not.

## Minimum configuration

Three flavors. **Default** — standby is simply "running is off":

```yaml
energy_profiler:
  devices:
    - name: tv
      power: sensor.tv_power
      energy: sensor.tv_energy
      running:
        trigger: power
        on_above: 15
        off_below: 10
      standby: true
```

This flavor **requires a `running:` block** — without it the family is skipped with a warning in the log. Note it can never report `poweroff`: it cannot distinguish idle-drawing from truly off.

**Standalone power range** — the vampire band, no running detection at all. Thresholds are **inverted** compared to `running:`: standby *starts* going down through `on_below`.

```yaml
      standby:
        trigger: power
        on_below: 8                # W, in standby below this…
        on_delay: "00:01:00"       # …held for 1 min
        off_above: 12              # W, out of standby above this
        off_delay: "00:00:10"
```

**Standalone template** — any custom condition:

```yaml
      standby:
        trigger: template
        available: "{{ has_value('media_player.console') }}"
        state: "{{ is_state('media_player.console', 'standby') }}"
```

## What you get

**The gatekeeper:**

| Entity | Unit | Description |
| --- | --- | --- |
| `binary_sensor.<p>_standby` 📈 | — | `on` while the device is in standby, per the configured flavor. In the default flavor it mirrors `…_running` inverted, so recording both is redundant |
| `sensor.<p>_standby_duration` 💤 | s | How long the current standby stretch has lasted (0 while not in standby) |

**The standby energy group (`<p>_standby_energy`):** the block from levels 1–4 once more, accumulated **only while the gatekeeper is on**.

Every id below exists twice: as `_lifetime` 💤 ↺ (shown) and as one `_<period>` 🚫 meter per configured period — e.g. `sensor.<p>_standby_energy_cost_lifetime` plus `…_cost_daily` / `_monthly` / `_yearly`.

| Entity | Requires | Description |
| --- | --- | --- |
| `sensor.<p>_standby_energy_lifetime` | — | Energy drawn while idle |
| `sensor.<p>_standby_energy_from_self_lifetime` / `…_from_grid_lifetime` | [L3](03-self-sufficiency.md) | How much of the waste was solar, how much was paid grid |
| `sensor.<p>_standby_energy_from_solar_lifetime` / `…_from_battery_lifetime` | [L4](04-solar-battery.md) | Solar/battery split inside the self share |
| `sensor.<p>_standby_energy_cost_lifetime` | [L2](02-cost.md) | What doing nothing cost you |
| `sensor.<p>_standby_energy_from_grid_savings_lifetime` / `…_from_grid_cost_lifetime` | [L2](02-cost.md) + [L3](03-self-sufficiency.md) | Savings and grid cost of the standby slice |
| `sensor.<p>_standby_energy_self_sufficiency_lifetime` | [L3](03-self-sufficiency.md) | Self-sufficiency % while idle (period meters are gauges) |

**Inventory —** fully configured, with `[daily, monthly, yearly]`: **38 new entities** (123 cumulative) — the gatekeeper, the duration, and 36 for the group.

If [Level 5](05-running.md) is also configured, `sensor.<p>_status` now reports the full ladder: `running` > `standby` > `poweroff`. With standby alone it reports `standby` / `poweron` (out of standby = actively drawing).

## Same protection as every other group

Sourced from the decoupled total lifetime, so while the gatekeeper is off *or unavailable* the baseline advances without accumulating — active-cycle or unknown energy is never mislabelled as standby.

## Example

[`examples/standby.yaml`](../../examples/standby.yaml) — the three flavors side by side.

## Next

Want per-run analytics — energy, cost and solar share of *each individual wash*? → **[Level 7 — Cycles](07-cycles.md)**
