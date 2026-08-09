# The UI surface

[← Back to README](../README.md)

The integration is configured in YAML, but it is **visible** in the UI: it appears under *Settings → Devices & Services*, with one device per profiled appliance and one for the house.

Nothing there is editable. The YAML block stays the single source of truth; the integration entry exists so Home Assistant will let it register devices, which it refuses to do for integrations that have no config entry. That is the only reason it is not a plain YAML integration anymore — opening it offers no options, and the entry itself stores nothing.

## The devices

| Device | What it holds |
| --- | --- |
| **Energy Profiler (system)** | The house readings every attribution derives from: live shares, the derived solar contribution, and the declared configuration |
| One per configured device | Every entity of that appliance — power, the three energy groups, cycles, and all their period meters |

Each appliance hangs off the system device (`via_device`), so the UI shows the house readings as the parent of everything derived from them.

## The system device

### Live house shares

Instantaneous, read straight from the flows. Convenient next to the per-device figures on a dashboard, and none of them needs a template.

| Entity | Unit | Built when |
| --- | --- | --- |
| `sensor.energy_profiler_from_self_percentage` | % | flows configured |
| `sensor.energy_profiler_from_grid_percentage` | % | flows configured |
| `sensor.energy_profiler_from_solar_percentage` | % | both channels exist |
| `sensor.energy_profiler_from_battery_percentage` | % | both channels exist |

With a single channel its share equals self-sufficiency, so it is not created twice.

> **These are not the per-device percentages over the same period.** The house ones are instantaneous readings of the flows; the per-device ones divide two accumulators, so a closed period meter gives the *energy-weighted* share. On a sunny afternoon followed by a grid-fed evening the two will differ, and both are right — they answer different questions. See [Level 3](levels/03-self-sufficiency.md#percentages-are-outputs-never-inputs).

### The derived contribution

| Entity | Unit | Built when |
| --- | --- | --- |
| `sensor.energy_profiler_power_from_solar` | W | `load` declared **and** a solar channel exists (i.e. `battery` declared too) |
| `sensor.energy_profiler_power_from_self` | W | `load` declared with no channels — same number, honest name |

The name claims only what the configuration supports. With a solar channel declared, the derived remainder *is* the solar contribution. With only `load` and `grid`, it is whatever is not coming from the grid — sun, wind, a battery you never declared — so it stays `from_self`, exactly like the per-device entities at that level.

This one earns its place. When the contribution is computed as `load − grid − battery`, that number lives only inside the splitter and nothing else can see it — yet every device's attribution depends on it.

Publishing it makes the flow configuration checkable. Put it on a chart for a day and it should look like a solar curve clipped by your own consumption: flat at zero overnight, rising through the morning, dropping when a big load pulls from the grid. If instead it sits at zero at noon, or tracks your production curve exactly (including what goes to the battery), the declared flows are wrong — and every per-device split is wrong in the same way, silently.

### The prosumption scores

Built from `energy_flows:` ([Level 8](levels/08-prosumption.md)) rather than from the power flows, and unlike everything above they are **per period, not instantaneous** — each divides two energy counters of the same window.

| Entity | Unit | Built when |
| --- | --- | --- |
| `sensor.energy_profiler_self_energy_lifetime` (+ `_<period>`) | kWh | `energy_flows` |
| `sensor.energy_profiler_self_sufficiency_percentage_lifetime` (+ `_<period>`) | % | `energy_flows` |
| `sensor.energy_profiler_self_consumption_percentage_lifetime` (+ `_<period>`) | % | + `production` |
| `sensor.energy_profiler_prosumption_percentage_lifetime` (+ `_<period>`) | % | + `production` |
| `sensor.energy_profiler_energy_balance` | kWh | all four counters |
| `sensor.energy_profiler_solar_ranking_<period>` | — | `energy_flows` |

Self-sufficiency and self-consumption divide the *same* self-consumed energy by two different denominators, and each is capped by the other side: in winter no behaviour pushes self-sufficiency past `production/consumption`, and in summer the same holds for self-consumption in reverse. Prosumption divides by whichever side was scarce, so it reads as a score of how well the two met **in time** rather than of how the plant is sized.

`sensor.energy_profiler_energy_balance` is the one to glance at first on a new setup: it compares the two independent readings of the self-consumed energy and should sit at noise around zero. A drift that grows means one of the four counters is measuring something else.

The ranking entity's state is the leading device; its attributes hold the ordered table plus `unprofiled_advantage_kwh` — what everything you have *not* profiled did, which is exact because the score is zero-sum across the house.

### The declared configuration

`sensor.energy_profiler_configuration` is a diagnostic entity: its state is the number of profiled devices, its attributes carry the declared price, periods and flows, which self channels were resolved, and whether solar is derived.

For the full picture — including each device's *resolved* config after the defaults are merged, and the live state of every flow sensor — use **Download diagnostics** on the integration page. That is the fastest way to answer "is this device actually using the flows I think it is?".

## Why the period meters are on the device pages

Roughly half of a device's entities are Lean meters (`_daily`, `_monthly`, `_yearly`) — the ones you actually chart. Home Assistant attaches an entity to a device only when the entity's platform is backed by a config entry, and [Lean Utility Meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter)'s platform is discovery-based with no entry of its own.

So Energy Profiler builds those meters on **its own** platform, using Lean's public `meter_from_spec`. They are still genuine Lean entities with all the Lean behaviour.

Lean's **repairs** still cover them: the checks are scheduled by the entity itself, not by the platform, so a meter that is not excluded from the recorder — or whose series has accumulated more long-term points than its cycle allows — raises the same issue it always did. Two details follow from the platform split, both handled:

- The issue is filed under **Lean Utility Meter** in the Repairs list, not under Energy Profiler. It is a Lean meter with a Lean diagnostic, so that is where it belongs; the issue text names the entity.
- The "points overage" repair offers to run `thin_history` for you. That fix flow resolves the entity's *owning platform* before calling, so the button reaches these meters. (Calling Lean's own service there would have been a silent no-op — the flow would report success while nothing was thinned. Lean ≥ 1.2.0 is required for the corrected routing.)

One thing does change, and it is worth knowing before you write an automation. Home Assistant registers entity services under the **platform's** domain, so the maintenance calls that reach these meters are:

| Call this | Not this |
| --- | --- |
| `energy_profiler.thin_history` | ~~`lean_utility_meter.thin_history`~~ |
| `energy_profiler.import_history` | ~~`lean_utility_meter.import_history`~~ |
| `energy_profiler.calibrate` | ~~`lean_utility_meter.calibrate`~~ |
| `energy_profiler.clear_history` | ~~`lean_utility_meter.clear_history`~~ |

Same behaviour, same parameters — the Lean implementations are re-registered verbatim. The `lean_utility_meter.*` services still exist and still serve meters you declared in Lean's own YAML; they simply no longer match these entities.

### Upgrading from an earlier version

The entity registry keys on *(domain, platform, unique id)*, so meters that used to be dispatched to Lean's platform are registered under it. Left alone, recreating them here would look like brand-new entities: the old rows would keep the entity ids and every meter would come back as `..._2`, orphaning its long-term statistics, which are keyed by entity id.

The integration removes those stale rows on first setup so the new entities reclaim the same ids and keep their history. It is deliberately narrow — only rows that are under Lean's platform, carry a unique id this integration generates, *and* already hold exactly the entity id about to be pinned. Each migration is logged at `INFO`. A Lean meter you defined yourself in YAML cannot match all three conditions and is never touched.

**One entity was renamed**, and this migration cannot cover it: `<base>_self_sufficiency_*` is now `<base>_from_self_percentage_*`, so that the four percentage entities share one naming shape (`from_<portion>_percentage`) instead of one of them carrying a name of its own. Renaming changes the entity id, and long-term statistics are keyed by entity id, so the old series is orphaned rather than moved.

If you want that history in the new meter, run `energy_profiler.import_history` on each new period meter with the old one as `source_entity` — that service exists precisely for this. The same applies to the cycle metrics, renamed from `cycle_completed_self_sufficiency` / `cycle_live_self_sufficiency` / `cycles_self_sufficiency_percentage_mean` to the matching `from_self_percentage` forms; those are live values rather than accumulators, so there is nothing to migrate.

## What is still YAML-only

Adding, editing or removing devices means editing the YAML and restarting Home Assistant. There is no options flow and no reload service yet.
