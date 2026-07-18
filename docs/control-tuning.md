# Control tuning — driving the heater from an external thermostat

The De'Longhi "My Comfort Hub" heaters (e.g. the Dragon 5 Connect, `TRD51024WIFI.G`)
have their temperature sensor mounted **next to the heating element**, where it reads
several degrees hotter than the actual room air while heating. Left to its own
thermostat, the unit cuts out early and the room never reaches the target. This note
characterises the heater's real behaviour and gives a recipe for controlling it well
from an external room sensor (e.g. with the
[Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) integration),
using **setpoint over/under-driving only** — no relay/plug switching, so it's silent.

All figures come from a ~75-minute instrumented run; raw data is in [`data/`](data/)
(see [Method](#method) at the end).

## TL;DR

- The element is **two-stage**: ~900 W + ~1200 W ≈ **~2.1 kW full**. Eco = the small
  stage only, **~950 W**.
- **Over-drive the setpoint to force heat, under-drive it to idle** — both silent:
  - `setpoint = 28` (max) + Eco off → full heat (see the modulation caveat below)
  - `setpoint = 28` + Eco on → **~950 W continuous, zero cycling**
  - `setpoint = 15` (below the internal sensor) → **0 W, silent idle**
- The internal sensor runs **~+3 °C hot** while heating and is reported only in whole
  degrees, laggily — **don't trust it**; thermostat off an independent room sensor.
- In a room with real heat loss, **Eco alone gently heats and holds with no cycling** —
  full power is only worth it for a faster cold start.

## Measured power modes

| Mode | How to command it | Measured power |
|---|---|---|
| Idle | `setpoint` ≤ internal sensor (e.g. 15) | **0 W** (silent) |
| Eco (hold) | Eco **on**, `setpoint` 28 | **~950 W**, dead steady |
| Full (boost) | Eco **off**, `setpoint` 28 | **~1300–2200 W** — modulated (see below) |

**Modulation caveat.** "Full" is only a steady ~2.2 kW from a **cold** start. Once the
internal sensor gets within a few degrees of the setpoint, the heater modulates between
its ~1300 W stage and ~2200 W on a ~5–15 s cycle (visible in
[`data/setpoint-profile-power.csv`](data/setpoint-profile-power.csv), minutes 14–25),
averaging ~1500 W. So over-driving to 28 does **not** guarantee constant full power once
the unit is warm.

## Heat-up and steady-state behaviour

Measured in a room with significant heat loss (a 2.2 kW burst raised the air only
~1.3 °C in 25 min):

- **Full (modulated, ~1500 W avg):** ~3 °C/hr room-air rise.
- **Eco (~950 W steady):** ~2 °C/hr — and it **net-heats**: at ~22–23 °C the room's heat
  loss is below 950 W, so Eco keeps climbing (it reached the 23 °C target on Eco alone;
  see [`data/setpoint-profile-roomair.csv`](data/setpoint-profile-roomair.csv)). Its
  equilibrium (loss = 950 W) is likely ~25–26 °C.
- **Eco steady-state has zero cycling** — after a brief settling it held 942–954 W
  continuously for 16+ minutes (minutes ~30–55 in the power data). This is the key
  result: Eco gives gentle, continuous, silent heat.

## Why the built-in thermostat isn't usable

The heater cuts the element when **its** sensor reaches the setpoint. Because that sensor
sits by the element, it reads ~+3 °C above room air during heating, so the unit shuts off
while the room is still ~3 °C short of target, then slow-cycles as the sensor cools.
The cloud also reports that sensor only in whole degrees and with lag (it sat at "25 °C"
for the entire 25-minute heat-up while room air rose 21→22.3 °C — see the shadow vs. air
data). **Conclusion: bypass it.** Pin the De'Longhi setpoint to the extremes and let an
external sensor do the real thermostatting.

## Versatile Thermostat recipe

Control everything through the **setpoint** (silent), thermostatted off an independent
room-air sensor.

1. **Expose two heater states as a template switch:**
   - `on`  → set De'Longhi **Eco on** + **setpoint 28**  (≈ 950 W continuous)
   - `off` → set De'Longhi **setpoint 15**                (0 W idle)
2. **Point Versatile Thermostat (`thermostat_over_switch`) at that switch**, with the
   external room sensor as its temperature source and a **±0.3–0.5 °C deadband**.
   Because Eco is gentle (~2 °C/hr), temperature swings are slow, so this yields roughly
   **1–2 silent setpoint flips per hour** — minimal cycling, no plug noise.
3. **Optional cold-start boost:** one automation — while the room sensor is **> ~1.5 °C
   below target**, set **Eco off** (full power) for a faster warm-up; within 1.5 °C,
   switch **Eco on**. That is the "full power for heat-up, Eco to hold" strategy.

Notes:
- In this integration, **Eco is the climate `eco` preset** (`climate.set_preset_mode`) and the
  setpoint is `climate.set_temperature` — there is no separate Eco switch entity.
- Never switch the mains/plug relay for thermostatting — it clicks. Setpoint and Eco
  commands are silent.
- If your target is at or above the Eco equilibrium (~25–26 °C here), you can simply
  leave Eco on continuously and it will hold with **no** switching at all.
- The numbers above are room-specific (heat loss, sensor placement, airflow). Re-run the
  method below in your own room to calibrate the boost threshold and equilibrium.

## Method

A ~75-minute run drove the heater through: full-power over-drive (setpoint 28, Eco off) →
Eco hold (Eco on) → idle test (setpoint 15) → reheat test (setpoint 28), logging three
streams by timestamp. Time in the data files is **minutes from heat start**.

| File | Source | Columns |
|---|---|---|
| [`data/setpoint-profile-power.csv`](data/setpoint-profile-power.csv) | in-line metering plug (on-change) | `elapsed_min, power_W` |
| [`data/setpoint-profile-roomair.csv`](data/setpoint-profile-roomair.csv) | independent room-air sensor | `elapsed_min, room_air_C` |
| [`data/setpoint-profile-shadow.csv`](data/setpoint-profile-shadow.csv) | heater cloud shadow (12 s poll) | `elapsed_min, phase, eco, internal_temp_C, setpoint_C, pcb_temp_C` |

The data is de-identified (relative time only; no device, account, network, or entity
identifiers). Approximate phase boundaries: over-drive heat 0–25 min, Eco hold 25–55 min,
idle 55–63 min, reheat 63–71 min.
