# Energy Insights Monitor

**Per-device energy intelligence for Home Assistant: energy, cost, solar self-sufficiency, appliance run cycles and standby waste — from just two sensors per device, configured entirely in YAML.**

Point it at a device's power and energy sensors and it builds the whole analytical stack for you:

- **Energy** — all-time total decoupled from the hardware sensor (survives plug swaps), plus per-cycle meters (daily / monthly / yearly / …)
- **Cost** — € accumulated at the price valid *at the moment of consumption*, projected cost rates (€/h, €/day, …)
- **Self-sufficiency** — how much of the device's energy came from your solar production vs the grid, what it saved you and what the grid imports cost, as instantaneous power, cumulative energy and percentages
- **Run cycles** — detects appliance runs (dishwasher, washing machine, A/C…), validates them against duration/energy limits, and tracks per-cycle values, means and totals; fires events you can automate on
- **Standby** — the "vampire" energy (and its cost) drawn while the device is *not* running

All cumulative series are backed by [Lean Utility Meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter): long-term statistics get **one consolidated row per closed cycle** instead of thousands of hourly rows, while the dashboards stay live. A fully-equipped device exposes 80+ entities but adds only a handful of rows per day to your database — provided the recorder is configured as documented in [Recorder Setup](docs/recorder.md).

## Requirements

Hard dependency on [lean_utility_meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter):
cumulative/cycle sensors reuse its Lean core. Install it first — without it, this
integration will refuse to set up.

## Quick Start

```yaml
energy_insights_monitor:
  defaults:
    energy_price: sensor.energy_price_purchase             # optional: enables the cost family
    self_sufficiency_source: sensor.home_self_sufficiency  # optional: enables the solar/grid split
    cycles: [daily, monthly, yearly]

  devices:
    - name: washing_machine
      power: sensor.washing_machine_power
      energy: sensor.washing_machine_energy
      run:                       # optional: enables run-cycle tracking
        trigger: power
        on_above: 5
        off_below: 2
        off_delay: "00:02:00"
      standby: true              # optional: enables standby tracking
```

Then configure the recorder — this part is **not optional**: the cycle meters write their own long-term statistics, and letting the recorder record them too corrupts the series with duplicate rows. [Recorder Setup](docs/recorder.md) tells you exactly what to include or exclude depending on how your system is set up.

## Documentation

| Page | What you'll find |
| --- | --- |
| [Recorder Setup](docs/recorder.md) | **Read this first.** What to exclude/include and why, with ready-made blocks for both exclude-based and include-based (whitelist) systems |
| [Configuration](docs/configuration.md) | Every option, grouped by area: base, shared defaults, run detection, cycle limits, standby |
| [Entities](docs/entities.md) | The complete catalog of entities a device can expose, grouped by family, with the meaning of each one |

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

The integration registers entity services under its own domain:

- `energy_insights_monitor.reset` — zero a resettable entity (lifetime accumulators, cycle counters, peak power); no-op on entities with nothing to reset
- `energy_insights_monitor.thin_history`, `import_history`, `clear_history`, `calibrate` — the [Lean maintenance services](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter/blob/master/docs/services.md), re-exposed so they can target this integration's cycle meters

The cycles family also fires `energy_insights_monitor_cycle_completed` / `_cycle_discarded` events for your own automations — payload documented in [Entities](docs/entities.md#events).

## Status

🚧 Pilot phase. All families are implemented (**power**, **energy**, **cost**, **self-sufficiency**, **cycles**, **standby**) and running in parallel with the legacy generator on a pilot device. Under validation: the end-of-period snapshot timing for the self-sufficiency percentage meters.

Successor to the `scripts/energy_monitor` code generator: instead of rendering
~66 static YAML packages, it creates the same entities dynamically from an
`energy_insights_monitor:` config block, preserving the historical entity ids.
