# Energy Profiler

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/nicola-spreafico/home-assistant-energy-profiler/actions/workflows/validate.yml/badge.svg)](https://github.com/nicola-spreafico/home-assistant-energy-profiler/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/nicola-spreafico/home-assistant-energy-profiler)](https://github.com/nicola-spreafico/home-assistant-energy-profiler/releases)
[![License: GPL-3.0](https://img.shields.io/github/license/nicola-spreafico/home-assistant-energy-profiler)](LICENSE)
[![GitHub Last Commit](https://img.shields.io/github/last-commit/nicola-spreafico/home-assistant-energy-profiler)](https://github.com/nicola-spreafico/home-assistant-energy-profiler/commits)
[![GitHub Issues](https://img.shields.io/github/issues/nicola-spreafico/home-assistant-energy-profiler)](https://github.com/nicola-spreafico/home-assistant-energy-profiler/issues)
[![Buy Me a Pizza](https://img.shields.io/badge/Buy%20me%20a%20pizza-%F0%9F%8D%95-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/mf3ebnouct)

<p align="center">
  <img src="custom_components/energy_profiler/brand/icon.png" alt="Energy Profiler">
</p>

**Per-device energy intelligence for Home Assistant: energy, cost, solar self-sufficiency, appliance run cycles and standby waste — from just two sensors per device, configured entirely in YAML.**

## Why this integration exists

> *"Your energy dashboard says the house is 70% self-sufficient. Good — but if
> you want to **improve** that number, which device do you act on? Maybe the
> dishwasher already runs at 95% and there is nothing left to optimize, while
> the washing machine sits at 20% — that is where the effort pays off, for
> example by washing when the sun is shining."*

> *"Did yesterday's washing-machine cycle actually run on the clean energy of
> the sun, or did it silently pull half of its load from the grid — and what
> did it cost you?"*

> *"How much money does the TV burn per year just sitting in standby, and is
> the bedroom A/C running longer per cycle than it used to?"*

Energy Profiler was created for these questions. House-level graphs tell you
*what* your self-sufficiency is, but not *where* to act to improve it — that
takes the same solar/grid/cost breakdown **per device**. The native **Energy
Dashboard** is great at the *house* level — total consumption, solar
production, grid import/export — and its individual-devices view stops at a
bar of kWh per device. Everything behind that number is missing, and that is
exactly what this integration provides:

| | Native Energy Dashboard | Energy Profiler |
| --- | --- | --- |
| **Per-device consumption** | total kWh only | energy split into **total / running / standby**, each with per-period meters |
| **Per-device solar share** | house-level only | solar-vs-grid (and optionally solar-vs-battery) split **per device**, as live power, energy and % |
| **Per-device cost** | house-level cost only | € per device at the tariff valid *at the moment of consumption*, plus savings and grid-import cost |
| **Appliance runs** | not tracked | cycles detected and validated, with per-run energy/cost/duration, means, lifetime totals |
| **Standby waste** | invisible | measured continuously, with the same cost/solar breakdown as useful consumption |
| **Automations** | none | events on completed/validated cycles and a ready-made `running`/`standby`/`poweroff` status |

## What you get

Point it at a device's power and energy sensors and it builds the whole analytical stack for you:

- **Energy in three symmetric groups** — **total**, **running-only** and **standby-only**: each group exposes the same block (energy, solar/grid split, cost, savings/grid-cost, self-sufficiency %, per-period meters), so separating useful consumption from "vampire" waste never costs you the solar or cost breakdown
- **Cost** — € accumulated at the price valid *at the moment of consumption*, projected cost rates (€/h, €/day, …)
- **Self-sufficiency** — how much of each group's energy came from your own production vs the grid, what it saved you and what the grid imports cost, as instantaneous power, cumulative energy and percentages; optionally split the self share further into **direct solar vs battery discharge** (`from_solar` / `from_battery`) — e.g. how much sun, how much battery and how much grid a washing-machine run actually used
- **Run cycles** — detects appliance runs (dishwasher, washing machine, A/C…), validates them against duration/energy limits, and tracks per-run values, means and totals; fires events you can automate on
- **Device status label** — a ready-made `running`/`standby`/`poweroff` enum for dashboards

All cumulative series are backed by [Lean Utility Meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter): long-term statistics get **one consolidated row per closed period** instead of thousands of hourly rows, while the dashboards stay live. A fully-equipped device exposes 80+ entities but adds only a handful of rows per day to your database — provided the recorder is configured as documented in [Recorder Setup](docs/recorder.md).

## Requirements

Hard dependency on [lean_utility_meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter):
cumulative/cycle sensors reuse its Lean core. Install it first — without it, this
integration will refuse to set up.

## Quick Start

### Only have a power sensor?

`energy:` is **required** per device — this integration does not derive it for you, since Home Assistant already ships a native way to do that. If your device only reports instantaneous power (no cumulative energy), add a core [Integration - Riemann sum integral](https://www.home-assistant.io/integrations/integration/) sensor to turn that power reading into energy first, then point `energy:` at the resulting sensor.

### Your first device

A `devices:` list, merged across package files. Two sensors are all it takes to start:

```yaml
energy_profiler:
  devices:
    - name: dishwasher
      power: sensor.dishwasher_power
      energy: sensor.dishwasher_energy
```

Then configure the recorder — this part is **not optional**: the period meters write their own long-term statistics, and letting the recorder record them too corrupts the series with duplicate rows. [Recorder Setup](docs/recorder.md) tells you exactly what to include or exclude depending on how your system is set up.

## The levels

A fully-equipped device exposes **173 entities** — which is a lot to meet all at once. So don't: the integration is built as a ladder, and every rung is useful on its own. Each level asks one question about what you already have, and answers with a specific set of sensors.

| Level | You have… | You get | New | Total |
| --- | --- | --- | --- | --- |
| **[1 — Energy](docs/levels/01-energy.md)** | a power and an energy sensor | consumption per period, on a database diet | 5 | 5 |
| **[2 — Cost](docs/levels/02-cost.md)** | …and an electricity price | € at the tariff of the moment, plus live projections | 8 | 13 |
| **[3 — Self-sufficiency](docs/levels/03-self-sufficiency.md)** | …and a self-sufficiency % | solar-vs-grid split per device, savings and grid cost | 22 | 35 |
| **[4 — Solar vs battery](docs/levels/04-solar-battery.md)** | …and a solar-share % | how much was sunshine, how much was the battery | 10 | 45 |
| **[5 — Running](docs/levels/05-running.md)** | a way to tell "on" from "off" | the whole block again, over running time only | 38 | 83 |
| **[6 — Standby](docs/levels/06-standby.md)** | a way to spot idle draw | the whole block again, over vampire waste | 38 | 121 |
| **[7 — Cycles](docs/levels/07-cycles.md)** | appliances that run in cycles | per-run energy, cost and solar share, with events | 52 | 173 |

Counts assume the default `periods: [daily, monthly, yearly]` and every optional source configured; fewer options mean fewer entities.

**Levels 1–4 ask what you can measure.** Each optional source adds a sub-block: a price brings cost, a self-sufficiency percentage brings the solar/grid split, a solar share splits that again into panels versus battery. They also compose — a price *and* a percentage together unlock savings and grid cost, which neither gives alone.

**Levels 5–7 ask which slice you measure it over.** They add no new kind of sensor: they replicate the block you already built over a gated slice of the consumption. Teach the integration to tell running from idle and you get the same energy, cost and solar breakdown for running time and for standby waste, separately. That multiplication is exactly why the total reaches 173 — and why it is far less to learn than the number suggests.

Stop at any rung. Level 1 alone is a complete, useful setup.

### The percentage sources

Levels 3 and 4 need one or two 0–100 sensors that are yours to provide — the share of consumption covered by local production, and the share of *that* coming straight from the panels. If your inverter integration does not expose them, both derive from the instantaneous power flows with a template sensor; the ready-made templates are in [Level 3](docs/levels/03-self-sufficiency.md#minimum-configuration) and [Level 4](docs/levels/04-solar-battery.md#minimum-configuration).

### Shared defaults — once for the whole system

The optional sources above are almost always the same for every device, so declare them once. `defaults:` goes in **exactly one** place: it is the system-wide baseline every device inherits. Any key can then be overridden by a single device, or opted out with `null`. Thanks to Home Assistant's package merge, this block can live in its own file while the devices are spread across other packages.

```yaml
energy_profiler:
  defaults:
    energy_price: sensor.energy_price_purchase             # level 2: the cost sub-block
    self_sufficiency_source: sensor.home_self_sufficiency  # level 3: the self/grid split
    solar_share_source: sensor.home_solar_share_of_self    # level 4: splits self into solar vs battery
    # battery_share_source: sensor.home_battery_share_of_self  # …or provide the battery share instead
    #                                                          # (mutually exclusive: one is the complement of the other)
    name_suffix: _em                   # entity prefix = <name> + this suffix
    live_update_interval: "00:15:00"   # throttle for the meters' live LTS upserts
    periods: [daily, monthly, yearly]  # meter windows: hourly..yearly
```

```yaml
energy_profiler:
  devices:
    - name: home_office
      power: sensor.home_office_power
      energy: sensor.home_office_energy
      self_sufficiency_source: null    # this device only: no solar split (drops levels 3-4)
      periods: [daily, monthly]        # fewer meter windows than the default
```

## Documentation

| Page | What you'll find |
| --- | --- |
| [Recorder Setup](docs/recorder.md) | **Read this first.** What to exclude/include and why, with ready-made blocks for both exclude-based and include-based (whitelist) systems |
| [The levels](#the-levels) | The guided path: [1 Energy](docs/levels/01-energy.md) → [2 Cost](docs/levels/02-cost.md) → [3 Self-sufficiency](docs/levels/03-self-sufficiency.md) → [4 Solar vs battery](docs/levels/04-solar-battery.md) → [5 Running](docs/levels/05-running.md) → [6 Standby](docs/levels/06-standby.md) → [7 Cycles](docs/levels/07-cycles.md). Each page: minimum config and the exact sensors it unlocks |
| [Entity reference](docs/entities.md) | Flat lookup: you see an entity, you want to know what it is, what unlocked it and how to record it |
| [Configuration](docs/configuration.md) | Every option, grouped by area: base, shared defaults, running detection, cycle analytics, standby |
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

- `energy_profiler.reset` — zero a resettable entity (lifetime accumulators, cycle counters, peak power); no-op on entities with nothing to reset
- The per-period meters are **native Lean entities**, so Lean's own services (`lean_utility_meter.thin_history`, `import_history`, `clear_history`, `calibrate`) target them directly

Details and the full entity lists in [Services & Actions](docs/services.md).

The cycles family also fires `energy_profiler_cycle_completed` / `_cycle_discarded` events for your own automations — payload documented in [Level 7 — Cycles](docs/levels/07-cycles.md#events).

## Status

🚧 Pilot phase. All families are implemented (**power**, **energy**, **cost**, **self-sufficiency**, **cycles**, **standby**) and running in parallel with the legacy generator on a pilot device. Under validation: the end-of-period snapshot timing for the self-sufficiency percentage meters.

Successor to the `scripts/energy_monitor` code generator: instead of rendering
~66 static YAML packages, it creates the same entities dynamically from an
`energy_profiler:` config block, preserving the historical entity ids.
