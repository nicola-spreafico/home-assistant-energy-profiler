# Level 1 — Energy

[← The levels](../../README.md#the-levels) · [Next: Cost →](02-cost.md)

> *"How much electricity does this device actually use — today, this month, this year?"*

The floor everyone starts from. Two sensors per device, and you get a clean per-period consumption history that stays cheap in the database.

**Prerequisites:** none.

> **Home Assistant devices:** peak power stays on **<name>**; cumulative and period energy appear on **<name> · Energy**.

## Minimum configuration

```yaml
energy_profiler:
  devices:
    - name: dishwasher
      power: sensor.dishwasher_power
      energy: sensor.dishwasher_energy
```

`power:` and `energy:` are both **required**. If your device only reports instantaneous power, create a core [Integration - Riemann sum](https://www.home-assistant.io/integrations/integration/) sensor first and point `energy:` at it — this integration deliberately does not derive energy from power, since Home Assistant already ships that natively.

Every entity id starts with the device **prefix** `<p>` = `<name>` + `name_suffix` (default `_em`), so this device produces `sensor.dishwasher_em_…`.

## What you get

| Entity | Unit | Description |
| --- | --- | --- |
| `sensor.<p>_power_max` 📈 ↺ | W | Running peak of the power sensor, kept across restarts until you reset it |
| `sensor.<p>_energy_lifetime` 💤 ↺ | kWh | The **decoupled all-time total**: it accumulates only positive deltas, so a meter reset, a firmware update or a plug swap never zeroes your history. Everything else in every level reads from this |
| `sensor.<p>_energy_<period>` 🚫 | kWh | One [Lean](https://github.com/nicola-spreafico/home-assistant-lean-utility-meter) meter per configured period: a live counter in the UI, one consolidated long-term row per closed period |

Markers (🚫 never record / 💤 exclude / 📈 worth recording / ↺ resettable) are defined in the [entity reference](../entities.md#markers).

**Inventory —** with the default `periods: [daily, monthly, yearly]`: **5 entities**.

```
sensor.<p>_power_max
sensor.<p>_energy_lifetime
sensor.<p>_energy_daily / _monthly / _yearly
```

Change the set with `periods:` (any of `hourly`, `daily`, `weekly`, `monthly`, `bimonthly`, `quarterly`, `yearly`) — every later level scales with the same list, so this choice multiplies through the whole path.

## Why `_energy_lifetime` matters

It is the single source every other level builds on, and the reason the whole stack survives hardware changes. Because it only ever adds positive deltas from your device's raw energy sensor, replacing the plug or resetting the device leaves the accumulator untouched — your per-period history stays continuous even when the underlying sensor restarts from zero.

## Before you go further

Configure the recorder now, not later: the period meters write their own long-term statistics, and letting the recorder also record them corrupts the series with duplicate rows. See [Recorder Setup](../recorder.md) — this part is **not optional**.

## Next

Have a sensor with your electricity price? → **[Level 2 — Cost](02-cost.md)**
