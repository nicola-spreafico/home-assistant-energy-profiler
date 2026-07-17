# Configuration

[← Back to README](../README.md)

Everything lives under a single `energy_insights_monitor:` block: one global `defaults` section plus a `devices` list. What each device enables is decided by **which options it declares** — there are no `enable_x: true` switches:

| You provide… | You get (the "family") |
| --- | --- |
| `power` + `energy` (required) | **power** + **energy** — peak power, all-time total, per-cycle energy meters |
| `energy_price` | **cost** — € accumulators, per-cycle cost meters, instant cost rates |
| `self_sufficiency_source` | **self-sufficiency** — solar/grid split (power, energy, %), and with a price also savings/grid-cost |
| `run:` block | **cycles** — run detection, per-cycle analytics, completed/live/mean values, events |
| `standby:` (bool or trigger block) | **standby** — idle energy and its cost; `true` gates on running-off, a trigger block defines a custom condition |

The full entity output of each family is cataloged in [Entities](entities.md).

**Splitting across packages:** Home Assistant merges the domain natively. Put `defaults:` in exactly one file and spread `devices:` across as many package files as you like — the device lists are concatenated and validated as a whole.

## Shared defaults (`defaults:`)

Global values inherited by every device that does not override them.

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `energy_price` | entity id | — | Sensor with the current energy purchase price (€/kWh). Enables the **cost** family for all devices |
| `self_sufficiency_source` | entity id | — | Sensor with the instantaneous home self-sufficiency percentage (0–100, e.g. solar production vs consumption). Enables the **self-sufficiency** family |
| `name_suffix` | string | `_em` | Appended to each device `name` to form the entity prefix (`<name><name_suffix>`); useful to namespace the whole fleet |
| `live_update_interval` | duration | `00:05:00` | Throttle for the Lean meters' live LTS upserts (cycle boundaries are always written exactly). Passed through to every cycle meter |
| `cycles` | list | `[daily, monthly, yearly]` | Which per-cycle meters every device gets: `hourly`, `daily`, `weekly`, `monthly`, `bimonthly`, `quarterly`, `yearly` |

## Device base options

| Option | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | slug | ✔ | Device slug; with `name_suffix` it forms the prefix of every entity id (`washing_machine` → `sensor.washing_machine_em_…`) |
| `power` | entity id | ✔ | The device's instantaneous power sensor (W) |
| `energy` | entity id | ✔ | The device's cumulative energy sensor (kWh). Resets and sensor swaps are tolerated: the integration accumulates only positive deltas into its own lifetime total |
| `switch` | entity id | — | The plug/switch powering the device. Accepted for forward compatibility; **no entity currently uses it** |
| `energy_price` | entity id or `null` | — | Per-device override of the default. Set `null` to opt this device **out** of the cost family even when a default is configured |
| `self_sufficiency_source` | entity id or `null` | — | Per-device override; `null` opts out of the self-sufficiency family |
| `live_update_interval` | duration | — | Per-device override of the default |
| `cycles` | list | — | Per-device override of the default cycle set |
| `notify_on_complete` | boolean | `false` | Accepted for config compatibility with the legacy generator, **currently a no-op**: build your own automation on the `energy_insights_monitor_cycle_completed` event instead |

## Run detection (`run:`)

Declaring a `run:` block enables the **cycles** family and creates `binary_sensor.<prefix>_running`, the gatekeeper every cycle and standby computation hangs on. Two trigger flavors:

**Power threshold** — for appliances recognizable by their draw:

```yaml
run:
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
| `on_delay` | `00:00:00` | how long the power must stay above `on_above` before the cycle opens (debounces spikes) |
| `off_delay` | `00:00:00` | how long it must stay below `off_below` before the cycle closes (bridges intra-cycle pauses, e.g. a dishwasher heating phase) |

**Template** — when a better signal than power exists (a `climate` state, a helper, …):

```yaml
run:
  trigger: template
  available: "{{ has_value('climate.bedroom_ac') }}"
  state: "{{ states('climate.bedroom_ac') != 'off' }}"
```

| Option | Required | Meaning |
| --- | --- | --- |
| `state` | ✔ | template that renders truthy while the device is running |
| `available` | ✔ | template that renders truthy when the signal itself is trustworthy; while false the running sensor goes unavailable instead of guessing |

## Cycle limits (`limits:`)

Optional plausibility checks applied when a cycle closes. A cycle failing any of them is **discarded**: its snapshot/completed/validation sensors are still written (so you can inspect it), but it does not increment the counters, totals or means, and the `…_cycle_discarded` event fires instead of `…_cycle_completed`.

```yaml
limits:
  min_duration: "00:05:00"
  max_duration: "12:00:00"
  min_energy: 0.05   # kWh
  max_energy: 10.0   # kWh
```

| Option | Rejected as |
| --- | --- |
| `min_duration` | `too_short` |
| `max_duration` | `too_long` |
| `min_energy` | `too_little_energy` |
| `max_energy` | `too_much_energy` |

The verdict (or `valid`) is exposed by `sensor.<prefix>_cycle_validation_status` and in the event payload.

## Standby (`standby:`)

Enables the **standby** family: energy accumulated while the device is in standby (plus its cost, when priced), gated on a dedicated `binary_sensor.<prefix>_standby`. Three flavors:

**Default** — standby is simply "not running". Requires the `run:` block (without running detection there is no notion of "idle"; the family is skipped with a warning). The standby sensor mirrors `…_running` inverted, and follows its availability:

```yaml
standby: true
```

**Power threshold** — standby while the draw sits in the vampire range. Does **not** require `run:`. Thresholds are inverted with respect to `run:` (standby is entered going *down*):

```yaml
standby:
  trigger: power
  on_below: 8            # W: standby when power drops below this…
  on_delay: "00:01:00"   # …for at least this long (default 0)
  off_above: 12          # W: standby ends above this (default: same as on_below)
  off_delay: "00:00:10"  # …for at least this long (default 0)
```

**Template** — any custom condition (a `media_player` state, a helper, …). Does **not** require `run:`:

```yaml
standby:
  trigger: template
  available: "{{ has_value('media_player.console') }}"
  state: "{{ is_state('media_player.console', 'standby') }}"
```

Whatever the flavor, energy is attributed to standby only while the gatekeeper is `on` — when it is `off` **or unavailable**, the baseline advances without accumulating, so uncertain periods are never counted as standby.

## Full example

See [`examples/full.yaml`](../examples/full.yaml) for a fleet mixing all of the above: shared defaults, a plain consumption device, a solar-split device, a cycle-tracked washing machine with limits, and a TV with standby tracking.
