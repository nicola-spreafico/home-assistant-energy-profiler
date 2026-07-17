# Energy Insights Monitor

**Per-device energy intelligence for Home Assistant: energy, cost, solar self-sufficiency, appliance run cycles and standby waste — from just two sensors per device, configured entirely in YAML.**

Point it at a device's power and energy sensors and it builds the whole analytical stack for you:

- **Energy** — all-time total decoupled from the hardware sensor (survives plug swaps), plus per-period meters (daily / monthly / yearly / …)
- **Cost** — € accumulated at the price valid *at the moment of consumption*, projected cost rates (€/h, €/day, …)
- **Self-sufficiency** — how much of the device's energy came from your solar production vs the grid, what it saved you and what the grid imports cost, as instantaneous power, cumulative energy and percentages
- **Run cycles** — detects appliance runs (dishwasher, washing machine, A/C…), validates them against duration/energy limits, and tracks per-run values, means and totals; fires events you can automate on
- **Standby** — the "vampire" energy (and its cost) drawn while the device is *not* running

All cumulative series are backed by [Lean Utility Meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter): long-term statistics get **one consolidated row per closed period** instead of thousands of hourly rows, while the dashboards stay live. A fully-equipped device exposes 80+ entities but adds only a handful of rows per day to your database — provided the recorder is configured as documented in [Recorder Setup](docs/recorder.md).

## Requirements

Hard dependency on [lean_utility_meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter):
cumulative/cycle sensors reuse its Lean core. Install it first — without it, this
integration will refuse to set up.

## Quick Start

One block, every supported configuration — each device shows a different combination (details per option in [Configuration](docs/configuration.md)):

```yaml
energy_insights_monitor:
  defaults:                       # shared by every device; each key can be overridden per device
    energy_price: sensor.energy_price_purchase             # optional: enables the cost family
    self_sufficiency_source: sensor.home_self_sufficiency  # optional: enables the solar/grid split
    name_suffix: _em              # entity prefix = <name> + this suffix
    live_update_interval: "00:15:00"   # throttle for the meters' live LTS upserts
    periods: [daily, monthly, yearly]  # meter windows: hourly..yearly

  devices:
    # 1) Minimal — energy + cost only (cost because a default price exists).
    - name: dishwasher
      power: sensor.dishwasher_power
      energy: sensor.dishwasher_energy

    # 2) Per-device overrides — opt OUT of a default with null, narrower periods.
    - name: home_office
      power: sensor.home_office_power
      energy: sensor.home_office_energy
      self_sufficiency_source: null    # no solar split for this device
      periods: [daily, monthly]

    # 3) Power-based running + full cycle analytics with plausibility limits.
    - name: washing_machine
      power: sensor.washing_machine_power
      energy: sensor.washing_machine_energy
      running:                         # signal: binary_sensor.<p>_running
        trigger: power
        on_above: 5                    # W, running above this…
        on_delay: "00:00:30"           # …held for 30 s
        off_below: 2                   # W, stopped below this…
        off_delay: "00:02:00"          # …held for 2 min (rides out pauses)
      cycle_tracking:                  # consumer: per-run analytics
        limits:                        # runs outside these are discarded
          min_duration: "00:05:00"
          max_duration: "04:00:00"
          min_energy: 0.05             # kWh
          max_energy: 5.0

    # 4) Template-based running + analytics without limits + default standby.
    - name: bedroom_ac
      power: sensor.bedroom_ac_power
      energy: sensor.bedroom_ac_energy
      running:
        trigger: template
        available: "{{ has_value('climate.bedroom_ac') }}"
        state: "{{ states('climate.bedroom_ac') != 'off' }}"
      cycle_tracking: true             # analytics, no limits
      standby: true                    # standby = not running

    # 5) Running signal ONLY (no analytics) + default standby: the signal
    #    exists just to define standby by difference.
    - name: tv
      power: sensor.tv_power
      energy: sensor.tv_energy
      running:
        trigger: power
        on_above: 15
        off_below: 10
      standby: true

    # 6) Standalone power-based standby (vampire range), no running at all.
    #    Inverted thresholds: standby starts going DOWN through on_below.
    - name: stereo
      power: sensor.stereo_power
      energy: sensor.stereo_energy
      standby:
        trigger: power
        on_below: 8                    # W, in standby below this…
        on_delay: "00:01:00"           # …held for 1 min
        off_above: 12                  # W, over standby above this
        off_delay: "00:00:10"

    # 7) Standalone template-based standby.
    - name: console
      power: sensor.console_power
      energy: sensor.console_energy
      standby:
        trigger: template
        available: "{{ has_value('media_player.console') }}"
        state: "{{ is_state('media_player.console', 'standby') }}"
```

Any device with at least one gatekeeper also gets `sensor.<prefix>_status` — a presentation-only label (`running` / `standby` / `poweroff` / `poweron`) handy on dashboards.

Then configure the recorder — this part is **not optional**: the period meters write their own long-term statistics, and letting the recorder record them too corrupts the series with duplicate rows. [Recorder Setup](docs/recorder.md) tells you exactly what to include or exclude depending on how your system is set up.

## Documentation

| Page | What you'll find |
| --- | --- |
| [Recorder Setup](docs/recorder.md) | **Read this first.** What to exclude/include and why, with ready-made blocks for both exclude-based and include-based (whitelist) systems |
| [Configuration](docs/configuration.md) | Every option, grouped by area: base, shared defaults, running detection, cycle analytics, standby |
| [Entities](docs/entities.md) | The complete catalog of entities a device can expose, grouped by family, with the meaning of each one |
| [Services & Actions](docs/services.md) | `reset` and the entities it supports; which entities are Lean-native meters and answer to Lean's own services |

### Examples

Focused configurations in the `examples/` directory:

| File | Shows |
|------|-------|
| `basic_consumption.yaml` | minimal per-device energy + cost |
| `self_sufficiency.yaml`  | solar/grid split + savings/grid-cost |
| `cycle_counting.yaml`    | run detection (power threshold / template) |
| `standby.yaml`           | idle "vampire" consumption |
| `full.yaml`              | shared defaults + a mixed fleet |

## Services

- `energy_insights_monitor.reset` — zero a resettable entity (lifetime accumulators, cycle counters, peak power); no-op on entities with nothing to reset
- The per-period meters are **native Lean entities**, so Lean's own services (`lean_utility_meter.thin_history`, `import_history`, `clear_history`, `calibrate`) target them directly

Details and the full entity lists in [Services & Actions](docs/services.md).

The cycles family also fires `energy_insights_monitor_cycle_completed` / `_cycle_discarded` events for your own automations — payload documented in [Entities](docs/entities.md#events).

## Status

🚧 Pilot phase. All families are implemented (**power**, **energy**, **cost**, **self-sufficiency**, **cycles**, **standby**) and running in parallel with the legacy generator on a pilot device. Under validation: the end-of-period snapshot timing for the self-sufficiency percentage meters.

Successor to the `scripts/energy_monitor` code generator: instead of rendering
~66 static YAML packages, it creates the same entities dynamically from an
`energy_insights_monitor:` config block, preserving the historical entity ids.
