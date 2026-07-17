# Entities — catalog overview

[← Back to README](../README.md)

The catalog is split by feature block — each page lists every entity of its block, with meanings and the explicit inventory:

| Page | Block | What it covers | Size* |
| --- | --- | --- | --- |
| [Base measurement](entities-base.md) | always on | power (peak, self/grid W), the **total energy group**: energy + cost + source splits, per period | 43 |
| [Running](entities-running.md) | `running:` | the running signal and the **running energy group** — consumption while the device is on | 37 |
| [Cycle tracking](entities-cycles.md) | `cycle_tracking:` | per-run analytics: boundaries, validation, 8-metric × 4-view matrix, durations, events | 52 |
| [Standby](entities-standby.md) | `standby:` | the standby gatekeeper and the **standby energy group** — the "vampire" waste | 38 |

\* entities for a fully-configured device with the default `[daily, monthly, yearly]` periods; fewer options = fewer entities. A fully-equipped device totals **171** (84 fixed + 29 per period), including the status label below.

Throughout the pages, `<p>` stands for the device prefix (`<name><name_suffix>`, e.g. `washing_machine_em`) and `<period>` for one entity per configured period. Which blocks a device gets is decided by its options — see [Configuration](configuration.md).

## Markers

Each entity carries two markers:

- **Recorder class** — how to treat it in the recorder (details in [Recorder Setup](recorder.md)):
  - 🚫 *never record* — a Lean period meter that writes its own long-term statistics; recording it corrupts the series
  - 💤 *exclude* — live view or restore-based accumulator; recording is pure database bloat
  - 📈 *worth recording* — changes at meaningful moments; its state history is useful
- **↺ resettable** — supports the `energy_insights_monitor.reset` entity service (zeroes the value). The 🚫 period meters are native Lean entities instead, maintained via Lean's own services — see [Services & Actions](services.md).

## Energy groups — total, running, standby

The three energy groups are **symmetric by construction**: each is the same sensor block (energy, self/grid split, solar/battery split, cost, savings/grid-cost, self-sufficiency %, all × period meters) over a differently-gated slice of the consumption:

| Group | `<base>` | Counts energy… | Exists when | Page |
| --- | --- | --- | --- | --- |
| **Total** | `<p>_energy` | always — any consumption, whatever the device state | always | [base](entities-base.md) |
| **Running** | `<p>_running_energy` | only while `binary_sensor.<p>_running` is on | `running:` | [running](entities-running.md) |
| **Standby** | `<p>_standby_energy` | only while `binary_sensor.<p>_standby` is on | `standby:` | [standby](entities-standby.md) |

The running and standby groups source the **decoupled total lifetime**, so they inherit its reset/plug-swap protection; while their gatekeeper is off *or unavailable* the baseline advances without accumulating, so uncertain periods are never counted. Note the accounting: `total ≈ running + standby + off-residual` only when both gates are configured and never overlap — each group is gated independently, there is no enforced identity.

## Device status — requires `running:` and/or `standby:`

One entity spans the blocks, derived from whichever gatekeepers exist:

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_status` 📈 | enum | **Presentation-only** label for dashboards; never consumed by internal logic. States depend on the configured signals: with both, `running` > `standby` > `poweroff`; with running only, `running`/`poweroff`; with standby only, `standby`/`poweron` (out of standby = actively drawing). With the default standby flavor `poweroff` never occurs (it cannot distinguish idle-drawing from truly off). Unavailable whenever a configured gatekeeper is unreadable |
