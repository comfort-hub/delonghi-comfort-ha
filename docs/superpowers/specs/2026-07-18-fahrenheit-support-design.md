# Fahrenheit support — unit-aware temperature (#5)

- **Date:** 2026-07-18
- **Issue:** comfort-hub/delonghi-comfort-ha#5
- **Status:** Approved design
- **Scope:** cross-repo — `delonghi-comfort` (library, 0.2.2) then `delonghi-comfort-ha`

## Problem

`climate.py` hardcodes `_attr_temperature_unit = UnitOfTemperature.CELSIUS` and a fixed
`15–28` setpoint range, and `async_set_temperature` always sends a **degC** command. A device
displaying Fahrenheit reports its `TempSetPoint`/`RoomTemp` in °F, so the entity misreports them
as Celsius, and the setpoint can't be driven in °F at all.

The library read side is already unit-aware (`MachineStatus.temperature_unit` / `.celsius` from
the `TempUnit` flag), and both `SetRoomTempRequest_degC` / `SetRoomTempRequest_degF` command
builders exist (`Command.TEMPERATURE_C` / `TEMPERATURE_F`, both writing `TempSetPoint` as whole
degrees). The only gaps: the library has no way to *send* a °F setpoint, and the climate entity
is Celsius-only.

## APK investigation (Fahrenheit bounds)

Decompiled the De'Longhi app (`unzip` + `strings` + a hand-rolled AArch64 disassembly of
`libapp.so`). Findings:
- Setpoints are **integers**, not doubles (28.0 and every °F candidate have zero IEEE-754
  occurrences), and **no float C↔F conversion** (`1.8`, `32.0`, `5/9`, `9/5`) is compiled in — so
  the app enforces a **hardcoded integer °F range**, not on-the-fly conversion. This validates
  using explicit °F bounds.
- The exact °F constants are not recoverable (inline Smi immediates). `59` and `82` do appear as
  constants (consistent with the range, not proof).
- **Chosen bounds: 41–82 °F** — confirmed directly from the app by the maintainer. Note min
  41 °F ≈ 5 °C is **lower** than a naive conversion of the °C minimum (15 °C), so the device's °F
  range is genuinely different, not a converted °C range — which is exactly why explicit bounds
  are needed.

## Design — library (`delonghi-comfort` 0.2.2)

Extend the setter with a unit parameter (positional-compatible — both existing callers pass the
value positionally, so nothing breaks):

```python
async def async_set_temperature(
    self, value: int, unit: TemperatureUnit = TemperatureUnit.CELSIUS
) -> None:
    """Set the target temperature in whole degrees of the given display unit."""
    command = (
        Command.TEMPERATURE_C
        if unit is TemperatureUnit.CELSIUS
        else Command.TEMPERATURE_F
    )
    await self.async_command(command, int(value))
```

Release as a `feat:` → release-please cuts **0.2.2** → PyPI.

**Library tests:** default sends `SetRoomTempRequest_degC`; `unit=FAHRENHEIT` sends
`SetRoomTempRequest_degF`; both carry the whole-degree value. (Existing `async_set_temperature(23)`
test keeps passing.)

## Design — HA integration (after 0.2.2)

### const
```python
MIN_TEMP_F: Final = 41  # 5 °C — app-confirmed, below the °C minimum
MAX_TEMP_F: Final = 82  # app-confirmed
```

### climate.py — report the device's native unit; let HA convert for display
- Drop `_attr_temperature_unit`, `_attr_min_temp`, `_attr_max_temp` class attrs; add properties:

```python
@property
def temperature_unit(self) -> str:
    return (
        UnitOfTemperature.CELSIUS
        if self.status.celsius
        else UnitOfTemperature.FAHRENHEIT
    )

@property
def min_temp(self) -> float:
    return MIN_TEMP if self.status.celsius else MIN_TEMP_F

@property
def max_temp(self) -> float:
    return MAX_TEMP if self.status.celsius else MAX_TEMP_F
```

- `async_set_temperature` passes the device unit (HA hands the entity the setpoint already in the
  entity's `temperature_unit`, which now equals the device unit):

```python
await self._async_guard(
    self.coordinator.client.async_set_temperature(
        int(kwargs[ATTR_TEMPERATURE]), unit=self.status.temperature_unit
    )
)
```

`status.temperature_unit` is the library `TemperatureUnit` enum, which is exactly what the setter
takes. `current_temperature` / `target_temperature` are unchanged (whole/tenths degrees in the
device unit; HA converts for the user's system unit).

### Pin bump
`manifest.json` `requirements: ["delonghi-comfort==0.2.2"]`; `pyproject.toml` `>=0.2.2`.

### HA tests (mock the coordinator status unit)
1. Celsius device → `temperature_unit == CELSIUS`, `min_temp/max_temp == 15/28`.
2. Fahrenheit device (`TempUnit` false) → `temperature_unit == FAHRENHEIT`, `min_temp/max_temp == 41/82`.
3. Set temperature on a Celsius device → `async_set_temperature(<v>, unit=CELSIUS)`.
4. Set temperature on a Fahrenheit device → `async_set_temperature(<v>, unit=FAHRENHEIT)`.

## Sequencing
1. Library 0.2.2 (feat + tests) → release-please → PyPI.
2. HA re-pin `==0.2.2`, climate changes + tests → release.

## Out of scope / risks
- The °F bounds (41–82) are app-confirmed by the maintainer; trivially adjustable in one const if a future °F device shows otherwise.
- Changing the device's display unit is already handled (`async_set_temp_unit`); this change only makes HA respect whatever unit the device is in.
