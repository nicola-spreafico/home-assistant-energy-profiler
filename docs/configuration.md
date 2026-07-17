# Configuration

[← Back to README](../README.md)

Everything lives under a single `energy_insights_monitor:` block: one global `defaults` section plus a `devices` list. What each device enables is decided by **which options it declares** — there are no `enable_x: true` switches:

| You provide… | You get |
| --- | --- |
| `power` + `energy` (required) | **power** + **energy** families — peak power, all-time total, per-period energy meters |
| `energy_price` | **cost** family — € accumulators, per-period cost meters, instant cost rates |
| `self_sufficiency_source` | **self-sufficiency** family — solar/grid split (power, energy, %), and with a price also savings/grid-cost |
| `running:` block | the running **signal** (`binary_sensor.<prefix>_running`) plus the **running energy group** — the same stack as the total, gated on it |
| `cycle_tracking:` (needs `running:`) | **cycles** family — per-run analytics: completed/live/mean values, counters, events |
| `standby:` (bool or trigger block) | the standby **signal** (`binary_sensor.<prefix>_standby`) plus the **standby energy group** — same stack, gated on it |
| `running:` and/or `standby:` | also `sensor.<prefix>_status` — a presentation-only enum label (`running`/`standby`/`poweroff`/`poweron`) for dashboards |

Two vocabulary notes, deliberate and consistent across docs and entities:

- **periods** are the Lean meter windows (`daily`, `monthly`, …) — the `periods` option;
- **cycles** are appliance runs (a wash program, an A/C session) — the `running:` signal and the `cycle_tracking:` analytics.

The full entity output of each family is cataloged in [Entities](entities.md).

**Splitting across packages:** Home Assistant merges the domain natively. Put `defaults:` in exactly one file and spread `devices:` across as many package files as you like — the device lists are concatenated and validated as a whole.

## Shared defaults (`defaults:`)

Global values inherited by every device that does not override them.

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `energy_price` | entity id | — | Sensor with the current energy purchase price (€/kWh). Enables the **cost** family for all devices |
| `self_sufficiency_source` | entity id | — | Sensor with the instantaneous home self-sufficiency percentage (0–100, e.g. solar production vs consumption). Enables the **self-sufficiency** family |
| `name_suffix` | string | `_em` | Appended to each device `name` to form the entity prefix (`<name><name_suffix>`); useful to namespace the whole fleet |
| `live_update_interval` | duration | `00:05:00` | Throttle for the Lean meters' live LTS upserts (period boundaries are always written exactly). Passed through to every meter |
| `periods` | list | `[daily, monthly, yearly]` | Which per-period meters every device gets: `hourly`, `daily`, `weekly`, `monthly`, `bimonthly`, `quarterly`, `yearly` |

## Device base options

| Option | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | slug | ✔ | Device slug; with `name_suffix` it forms the prefix of every entity id (`washing_machine` → `sensor.washing_machine_em_…`) |
| `power` | entity id | ✔ | The device's instantaneous power sensor (W) |
| `energy` | entity id | ✔ | The device's cumulative energy sensor (kWh). Resets and sensor swaps are tolerated: the integration accumulates only positive deltas into its own lifetime total |
| `energy_price` | entity id or `null` | — | Per-device override of the default. Set `null` to opt this device **out** of the cost family even when a default is configured |
| `self_sufficiency_source` | entity id or `null` | — | Per-device override; `null` opts out of the self-sufficiency family |
| `live_update_interval` | duration | — | Per-device override of the default |
| `periods` | list | — | Per-device override of the default period set |

## Running detection (`running:`)

A **signal**: declaring it creates `binary_sensor.<prefix>_running` and enables the **running energy group** — the same energy/split/cost stack as the total, accumulated only while running (see [Entities](entities.md#energy-groups--total-running-standby)). Other consumers hang on the signal explicitly: [`cycle_tracking:`](#cycle-analytics-cycle_tracking) for run analytics, and the default flavor of [`standby:`](#standby-standby). Unlike the cycles family, the running group counts *every* running moment, validated or not — it is what lets you split running vs standby consumption without tracking cycles.

Two trigger flavors:

**Power threshold** — for appliances recognizable by their draw:

```yaml
running:
  trigger: power
  on_above: 5          # W: running when power rises above this…
  on_delay: "00:00:30" # …for at least this long (default 0 = immediately)
  off_below: 2         # W: stopped when power falls below this…
  off_delay: "00:02:00"# …for at least this long (default 0)
```

| Option | Default | Meaning |
| --- | --- | --- |
| `on_above` | `0` | power (W) above which the device counts as running |
| `off_below` | `1` | power (W) below which it counts as stopped |
| `on_delay` | `00:00:00` | how long the power must stay above `on_above` before turning on (debounces spikes) |
| `off_delay` | `00:00:00` | how long it must stay below `off_below` before turning off (bridges intra-run pauses, e.g. a dishwasher heating phase) |

**Template** — when a better signal than power exists (a `climate` state, a helper, …):

```yaml
running:
  trigger: template
  available: "{{ has_value('climate.bedroom_ac') }}"
  state: "{{ states('climate.bedroom_ac') != 'off' }}"
```

| Option | Required | Meaning |
| --- | --- | --- |
| `state` | ✔ | template that renders truthy while the device is running |
| `available` | ✔ | template that renders truthy when the signal itself is trustworthy; while false the running sensor goes unavailable instead of guessing |

## Cycle analytics (`cycle_tracking:`)

The analytics **consumer** of the running signal: counts each run with its duration, energy, cost, solar split, … (the full output is in [Entities](entities.md#cycles--requires-running-and-cycle_tracking)). Requires `running:`; without it the family is skipped with a warning.

```yaml
cycle_tracking: true          # analytics, no plausibility limits
# or
cycle_tracking:
  limits:
    min_duration: "00:05:00"
    max_duration: "12:00:00"
    min_energy: 0.05   # kWh
    max_energy: 10.0   # kWh
```

`limits` are optional plausibility checks applied when a run ends. A run failing any of them is **discarded**: its snapshot/completed/validation sensors are still written (so you can inspect it), but it does not increment the counters, totals or means, and the `…_cycle_discarded` event fires instead of `…_cycle_completed`.

| Limit | Rejected as |
| --- | --- |
| `min_duration` | `too_short` |
| `max_duration` | `too_long` |
| `min_energy` | `too_little_energy` |
| `max_energy` | `too_much_energy` |

The verdict (or `valid`) is exposed by `sensor.<prefix>_cycle_validation_status` and in the event payload.

## Standby (`standby:`)

Enables the **standby energy group**: the full energy stack (energy, solar/grid split, costs, self-sufficiency % — same block as the total and running groups) accumulated while the device is in standby, gated on a dedicated `binary_sensor.<prefix>_standby`, plus the live `…_standby_duration`. Three gatekeeper flavors:

**Default** — standby is simply "not running". Requires the `running:` block (without the signal there is no notion of "idle"; the family is skipped with a warning) — but **not** `cycle_tracking`: a device can define running purely to give standby its complement. The standby sensor mirrors `…_running` inverted, and follows its availability:

```yaml
standby: true
```

**Power threshold** — standby while the draw sits in the vampire range. Does **not** require `running:`. Thresholds are inverted with respect to `running:` (standby is entered going *down*):

```yaml
standby:
  trigger: power
  on_below: 8            # W: standby when power drops below this…
  on_delay: "00:01:00"   # …for at least this long (default 0)
  off_above: 12          # W: standby ends above this (default: same as on_below)
  off_delay: "00:00:10"  # …for at least this long (default 0)
```

**Template** — any custom condition (a `media_player` state, a helper, …). Does **not** require `running:`:

```yaml
standby:
  trigger: template
  available: "{{ has_value('media_player.console') }}"
  state: "{{ is_state('media_player.console', 'standby') }}"
```

Whatever the flavor, energy is attributed to standby only while the gatekeeper is `on` — when it is `off` **or unavailable**, the baseline advances without accumulating, so uncertain periods are never counted as standby.

## Full example

See [`examples/full.yaml`](../examples/full.yaml) for a fleet mixing all of the above: shared defaults, a plain consumption device, a solar-split device, a cycle-tracked washing machine with limits, a TV with running + standby but no analytics, and a stereo with standalone standby.
