# Energy Insights Monitor (Home Assistant custom integration)

Per-device energy monitoring (energy, cost, self-sufficiency, cycles, standby)
derived from a device's real power/energy sensors — configured entirely in YAML.

Successor to the `scripts/energy_monitor` code generator: instead of rendering
~66 static YAML packages, it creates the same entities dynamically from an
`energy_insights_monitor:` config block.

## Requirements

Hard dependency on [lean_utility_meter](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter):
cumulative/cycle sensors reuse its Lean core (one consolidated LTS row per cycle).
Install it first — without it, this integration will refuse to set up.

## Examples

See the `examples/` directory for focused configurations:

| File | Shows |
|------|-------|
| `basic_consumption.yaml` | minimal per-device energy + cost |
| `self_sufficiency.yaml`  | solar/grid split + savings/grid-cost |
| `cycle_counting.yaml`    | run detection (power threshold / template) |
| `standby.yaml`           | idle "vampire" consumption |
| `full.yaml`              | shared defaults + a mixed fleet |

## Status

🚧 In development. Implemented: the **energy**, **cost** and **self-sufficiency**
families (Lean-backed cycle meters + live source accumulators). The **cycles** and
**standby** families are deferred — their config validates but no entities are
created yet. LTS consolidation of the self-sufficiency **percentages** is pending
pilot validation.
