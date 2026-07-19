# Climate honesty & optimistic control — `hvac_action`, optimistic writes, unconfirmed-command repair

- **Date:** 2026-07-19
- **Status:** Approved design
- **Scope:** `delonghi-comfort-ha` only (no library change)

## Problem

Two findings from benchmarking comparable cloud, self-regulating, event-driven heaters
(Overkiz/Atlantic, Mill, Adax, LG ThinQ, Tuya, Nest, Ecobee, Netatmo, Honeywell, Tado —
source-verified against `home-assistant/core`):

1. **`hvac_action` is over-claimed.** The shadow has no "element is heating" flag, so
   `climate.py` *derives* heating/idle from `current_temperature` vs `target` with a deadband.
   That reading is event-driven and often stale, and essentially **no device integration derives
   `hvac_action` from a temp-vs-target deadband** — it is a helper-only pattern
   (`generic_thermostat`). Peers with no flag (evohome, Adax, core Tuya, Sensibo, LG ThinQ,
   basic Overkiz) simply return `None`.
2. **Control feels sluggish.** The device echoes a command into its shadow only on the next
   event push (seconds to ~20 s observed), so the entity doesn't reflect a setpoint/power change
   until then. Peers (Sensibo, Tado) do a short **optimistic** write of the commanded value, then
   reconcile against the device's echo.

Optimism introduces a risk the maintainer flagged: if a command is accepted but silently never
applied, an optimistic value that just reverts could leave the user believing the heater is
on/off when it isn't. That must be surfaced, not silently reverted.

## Goals

1. `hvac_action` → `None` (drop the deadband derivation).
2. Optimistic write on command, reconciled against the device echo.
3. Surface a command that was **acked but never confirmed** so the user is never misled.

## Non-goals

- No external-temperature-sensor config option — that is helper territory
  (`generic_thermostat` / Versatile Thermostat), confirmed by the benchmark. Users keep layering
  VTherm `over_climate` for regulation on an external sensor.
- No library change; no change to `current_temperature` (keep reporting the device's last value),
  availability (stays connectivity-based), or the `last_reported` sensor.

## Design

### 1. `hvac_action` → `None`

- Delete the `hvac_action` property from `DelonghiClimate` so it inherits `ClimateEntity`'s
  default `None`.
- Delete the now-dead `HVAC_ACTION_DEADBAND` constant, the `_last_hvac_action` field, and the
  `HVACAction` import if unused.
- `hvac_mode` (off / heat / auto) already carries the meaningful state; `None` is the
  peer-correct choice for a device with no heating flag.

### 2. Optimistic write on command

Model overrides at the **derived-property level** (not raw shadow fields): `_optimistic_hvac_mode`,
`_optimistic_target`, `_optimistic_preset` (each `None` when not pending).

- The `hvac_mode` / `target_temperature` / `preset_mode` properties return the override when set,
  else the value derived from `self.status`.
- Each command method, **after the command acks** (so a rejected command never shows a fake
  state), sets the matching override, calls `self.async_write_ha_state()`, then
  `await self.coordinator.async_request_refresh()`:
  - `async_set_temperature` → `_optimistic_target = <value>`
  - `async_turn_off` → `_optimistic_hvac_mode = OFF`; `async_turn_on` → `HEAT`
  - `async_set_hvac_mode(mode)` → `_optimistic_hvac_mode = mode`
  - `async_set_preset_mode(preset)` → `_optimistic_preset = preset`
- **Reconciliation** (`_handle_coordinator_update`): for each pending override, if the value
  derived from `self.status` now equals the override, clear it (confirmed). Uses a helper that
  computes the "real" derived value without consulting the override.
- **Timeout** (`COMMAND_CONFIRM_TIMEOUT_SECONDS = 60`, one poll cycle, via `async_call_later`):
  scheduled/rescheduled whenever an override is set; on fire, revert any still-pending overrides
  and run the unconfirmed-command handling (§3). Cancelled when all overrides clear, and in
  `async_will_remove_from_hass`.

`always_update=False` is unaffected: a real command changes the shadow, so the coordinator still
notifies; only genuinely unchanged idle polls are deduped.

### 3. Unconfirmed-command surfacing

Two failure modes, handled distinctly:

- **A — not acked (immediate):** the library setter waits for `Response: OK`; a
  timeout/rejection raises, and `_async_guard` already maps it to a visible `HomeAssistantError`
  on the service call. The optimistic write happens *after* the ack, so no fake state is shown.
  No change needed.
- **B — acked but never confirmed (timeout fires):** revert the pending overrides to truth and
  raise a **Repair issue** via `homeassistant.helpers.issue_registry.async_create_issue` —
  deduped per config entry (fixed issue id, e.g. `command_unconfirmed`), `IssueSeverity.WARNING`,
  translated ("… didn't confirm a recent command; its state may differ from what you set"). The
  issue is **cleared** (`async_delete_issue`) the next time any override is confirmed (proving
  the device is responding again), and on unload.

### Files

- `custom_components/delonghi_comfort/climate.py` — all three changes.
- `custom_components/delonghi_comfort/const.py` — `COMMAND_CONFIRM_TIMEOUT_SECONDS`.
- `custom_components/delonghi_comfort/strings.json` + `translations/en.json` — the
  `issues.command_unconfirmed` title/description.

## Testing (TDD)

1. `hvac_action` is `None` whether the heater is off or on.
2. `async_set_temperature` → `target_temperature` reflects the commanded value **immediately**
   (before any coordinator update), and the setter was called.
3. Reconciliation: a coordinator update whose status **matches** the override clears it (property
   returns the coordinator value again); a **non-matching** update keeps the override pending.
4. Timeout: firing with an override still unconfirmed reverts the property to the coordinator
   value **and** creates the `command_unconfirmed` Repair issue.
5. A subsequent **confirmed** command clears the Repair issue.
6. Not-acked command (setter raises `CommandTimeoutError`) → `HomeAssistantError`, and no
   optimistic value is shown.

## Out of scope / risks

- 60 s timeout is a balance: long enough to avoid false alarms on a slow-but-successful echo
  (~20 s observed), short enough to revert promptly on genuine failure. One const, tunable.
- The Repair issue is intentionally coarse ("a recent command") and deduped, to avoid
  notification storms; it is not per-command.
- Reverting to the device's last-reported value on timeout means the display returns to *truth*
  (possibly itself stale) — the `last_reported` sensor continues to expose that staleness.
- On timeout the entity **re-reconciles** before alarming: a no-op command, or an echo whose
  unchanged shadow the coordinator deduped (`always_update=False`), is recognised as already
  satisfied and clears silently — no false issue. The Repair issue is cleared only on a genuine
  pending→confirmed transition (or unload), never by a routine idle poll.
- Known minor edge: if the user changes the device's unit (°C↔°F) within the confirm window of a
  setpoint command, the pending target (an integer in the command-time unit) can't match the
  reported setpoint in the new unit, so it reverts and raises one (accurate-display, spurious-
  warning) issue. This requires a unit flip inside a 60 s window and is left as-is.
