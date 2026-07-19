# Climate honesty & optimistic control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the De'Longhi climate entity honest about `hvac_action` and responsive to commands, and never leave the user believing a wrong on/off state.

**Architecture:** Three focused changes in `climate.py`: (1) drop the derived `hvac_action`; (2) hold short-lived optimistic overrides for the derived control properties, reconciled against the coordinator echo; (3) a 60 s confirm timeout that reverts an unconfirmed override and raises a deduped Repair issue.

**Tech Stack:** Home Assistant `ClimateEntity` + `DataUpdateCoordinator`, `homeassistant.helpers.event.async_call_later`, `homeassistant.helpers.issue_registry`. Tests: `pytest` + `pytest_homeassistant_custom_component`.

## Global Constraints

- Integration-only change — **no library change, no dependency/version bump** (release-please sets the integration version from commits).
- `current_temperature`, availability (connectivity-based), and the `last_reported` sensor are unchanged.
- Only built-in `HVACMode` / `PRESET_*` values; follow existing `climate.py` style.
- Run checks from repo root with `./.venv/bin/python -m pytest`, `./.venv/bin/ruff ...`, `./.venv/bin/python -m mypy custom_components/delonghi_comfort`.

## File structure

- `custom_components/delonghi_comfort/climate.py` — all three behaviour changes.
- `custom_components/delonghi_comfort/const.py` — `COMMAND_CONFIRM_TIMEOUT_SECONDS`.
- `custom_components/delonghi_comfort/strings.json` + `translations/en.json` — `issues.command_unconfirmed`.
- `tests/test_climate.py` — hvac_action + optimistic + reconciliation.
- `tests/test_controls.py` (or test_climate.py) — timeout + Repair issue.

---

### Task 1: `hvac_action` → `None`

**Files:**
- Modify: `custom_components/delonghi_comfort/climate.py` (remove property + deadband + field + import)
- Test: `tests/test_climate.py`

**Interfaces:**
- Produces: `DelonghiClimate` no longer exposes `hvac_action` (inherits `ClimateEntity` default `None`).

- [ ] **Step 1: Failing test** — add to `tests/test_climate.py`:

```python
async def test_hvac_action_is_omitted(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """No heating flag in the cloud -> we don't claim an hvac_action."""
    await _setup(hass, mock_config_entry, mock_client)  # existing helper; on-heat status
    state = hass.states.get(hass.states.async_entity_ids("climate")[0])
    assert state.attributes.get("hvac_action") is None
```

*(If `test_climate.py` has no `_setup` helper, set up inline like the other tests in that file.)*

- [ ] **Step 2: Run — expect FAIL** (currently derives `HVACAction.HEATING`/`IDLE`):
`./.venv/bin/python -m pytest tests/test_climate.py::test_hvac_action_is_omitted -q`

- [ ] **Step 3: Implement** — in `climate.py`:
  - Delete the whole `hvac_action` property (the `@property def hvac_action` block).
  - Delete the `HVAC_ACTION_DEADBAND = 0.5` constant and its comment.
  - Delete `_last_hvac_action: HVACAction | None = None`.
  - Remove `HVACAction` from the `homeassistant.components.climate` import.

- [ ] **Step 4: Run — expect PASS** (and full file): `./.venv/bin/python -m pytest tests/test_climate.py -q`, then `./.venv/bin/ruff check custom_components tests && ./.venv/bin/python -m mypy custom_components/delonghi_comfort`

- [ ] **Step 5: Commit**: `git commit -am "fix: omit hvac_action (no heating flag; stop deriving from stale temp)"`

---

### Task 2: Optimistic overrides + reconciliation

**Files:**
- Modify: `custom_components/delonghi_comfort/climate.py`
- Test: `tests/test_climate.py`

**Interfaces:**
- Produces: `DelonghiClimate` fields `_optimistic_hvac_mode: HVACMode | None`, `_optimistic_target: int | None`, `_optimistic_preset: str | None`; helpers `_real_hvac_mode()`, `_real_preset_mode()`, `_set_optimistic(*, hvac_mode=None, target=None, preset=None)`, `_has_pending()`; overridden `_handle_coordinator_update`. (Timeout hook `_schedule_confirm_timeout()` / `_confirm_all()` are stubs here, filled in Task 3.)

- [ ] **Step 1: Failing tests** — add to `tests/test_climate.py`:

```python
async def test_set_temperature_is_optimistic(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """After set_temperature, target reflects the commanded value before any echo."""
    await _setup(hass, mock_config_entry, mock_client)  # status TempSetPoint=22, heat mode
    cid = hass.states.async_entity_ids("climate")[0]
    await hass.services.async_call(
        "climate", "set_temperature",
        {"entity_id": cid, "temperature": 25}, blocking=True,
    )
    assert hass.states.get(cid).attributes["temperature"] == 25  # optimistic (echo still 22)


async def test_optimistic_cleared_when_device_confirms(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """When the coordinator's status matches the override, the override is dropped."""
    await _setup(hass, mock_config_entry, mock_client)
    cid = hass.states.async_entity_ids("climate")[0]
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": cid, "temperature": 25}, blocking=True
    )
    # Device now reports the new setpoint; a refresh confirms it.
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported({**_REPORTED, "TempSetPoint": 25})
    )
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    coordinator = mock_config_entry.runtime_data
    assert coordinator.data.target_temperature == 25
    assert hass.states.get(cid).attributes["temperature"] == 25  # now the real value
```

*(Import `AsyncMock`, `MachineStatus`, and the module `_REPORTED` from conftest at the top of the test file if not already present.)*

- [ ] **Step 2: Run — expect FAIL** (optimistic value not shown; second test may pass trivially — that's fine, first is the driver):
`./.venv/bin/python -m pytest tests/test_climate.py::test_set_temperature_is_optimistic -q`

- [ ] **Step 3: Implement** — in `climate.py`:
  - Add `from homeassistant.core import callback` to the runtime imports (currently only under TYPE_CHECKING).
  - Add fields to `DelonghiClimate`:
    ```python
    _optimistic_hvac_mode: HVACMode | None = None
    _optimistic_target: int | None = None
    _optimistic_preset: str | None = None
    ```
  - Add "real" helpers and make the three control properties prefer the override:
    ```python
    def _real_hvac_mode(self) -> HVACMode:
        if not self.status.is_on:
            return HVACMode.OFF
        return HVACMode.AUTO if self.status.schedule_enabled else HVACMode.HEAT

    def _real_preset_mode(self) -> str:
        return PRESET_ECO if self.status.eco else PRESET_NONE

    @property
    def hvac_mode(self) -> HVACMode:
        """Optimistic override while a command is pending, else the reported state."""
        if self._optimistic_hvac_mode is not None:
            return self._optimistic_hvac_mode
        return self._real_hvac_mode()

    @property
    def target_temperature(self) -> int | None:
        """Optimistic override while a command is pending, else the reported setpoint."""
        if self._optimistic_target is not None:
            return self._optimistic_target
        return self.status.target_temperature

    @property
    def preset_mode(self) -> str:
        """Optimistic override while a command is pending, else the reported preset."""
        if self._optimistic_preset is not None:
            return self._optimistic_preset
        return self._real_preset_mode()
    ```
  - Add the override setter (timeout hooks are added in Task 3 — leave a stub method `_schedule_confirm_timeout` that does nothing yet, or add both now; recommended: add the stubs now to avoid churn):
    ```python
    def _set_optimistic(
        self,
        *,
        hvac_mode: HVACMode | None = None,
        target: int | None = None,
        preset: str | None = None,
    ) -> None:
        if hvac_mode is not None:
            self._optimistic_hvac_mode = hvac_mode
        if target is not None:
            self._optimistic_target = target
        if preset is not None:
            self._optimistic_preset = preset
        self.async_write_ha_state()
        self._schedule_confirm_timeout()

    def _has_pending(self) -> bool:
        return (
            self._optimistic_hvac_mode is not None
            or self._optimistic_target is not None
            or self._optimistic_preset is not None
        )

    def _schedule_confirm_timeout(self) -> None:  # filled in Task 3
        pass

    def _confirm_all(self) -> None:  # filled in Task 3
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        """Clear each optimistic override the device has now confirmed, then write state."""
        if (
            self._optimistic_hvac_mode is not None
            and self._real_hvac_mode() == self._optimistic_hvac_mode
        ):
            self._optimistic_hvac_mode = None
        if (
            self._optimistic_target is not None
            and self.status.target_temperature == self._optimistic_target
        ):
            self._optimistic_target = None
        if (
            self._optimistic_preset is not None
            and self._real_preset_mode() == self._optimistic_preset
        ):
            self._optimistic_preset = None
        if not self._has_pending():
            self._confirm_all()
        super()._handle_coordinator_update()
    ```
  - Set the override after each command's ack (add one line before the existing `async_request_refresh()`):
    - `async_turn_on`: `self._set_optimistic(hvac_mode=HVACMode.HEAT)`
    - `async_turn_off`: `self._set_optimistic(hvac_mode=HVACMode.OFF)`
    - `async_set_hvac_mode`: `self._set_optimistic(hvac_mode=hvac_mode)`
    - `async_set_preset_mode`: `self._set_optimistic(preset=preset_mode)`
    - `async_set_temperature`: `self._set_optimistic(target=int(kwargs[ATTR_TEMPERATURE]))`

- [ ] **Step 4: Run — expect PASS**: `./.venv/bin/python -m pytest tests/test_climate.py -q`, then ruff + mypy.

- [ ] **Step 5: Commit**: `git commit -am "feat: optimistic climate control reconciled against the device echo"`

---

### Task 3: Confirm timeout + unconfirmed-command Repair issue

**Files:**
- Modify: `climate.py`, `const.py`, `strings.json`, `translations/en.json`
- Test: `tests/test_climate.py`

**Interfaces:**
- Consumes: Task 2's overrides + `_set_optimistic`/`_confirm_all` stubs.
- Produces: real `_schedule_confirm_timeout`/`_confirm_all`, `_confirm_timeout` callback, `async_will_remove_from_hass`; `const.COMMAND_CONFIRM_TIMEOUT_SECONDS`; issue id `f"command_unconfirmed_{entry_id}"`.

- [ ] **Step 1: Failing test** — add to `tests/test_climate.py`:

```python
async def test_unconfirmed_command_reverts_and_raises_issue(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A command the device never confirms reverts to truth and raises a Repair issue."""
    from homeassistant.helpers import issue_registry as ir

    from custom_components.delonghi_comfort.const import (
        COMMAND_CONFIRM_TIMEOUT_SECONDS,
        DOMAIN,
    )

    await _setup(hass, mock_config_entry, mock_client)  # status stays TempSetPoint=22
    cid = hass.states.async_entity_ids("climate")[0]
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": cid, "temperature": 25}, blocking=True
    )
    assert hass.states.get(cid).attributes["temperature"] == 25  # optimistic

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=COMMAND_CONFIRM_TIMEOUT_SECONDS + 1)
    )
    await hass.async_block_till_done()

    assert hass.states.get(cid).attributes["temperature"] == 22  # reverted to truth
    issue_id = f"command_unconfirmed_{mock_config_entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
```

*(Add imports at the top of the test file: `from datetime import timedelta`, `from homeassistant.util import dt as dt_util`, `from pytest_homeassistant_custom_component.common import async_fire_time_changed`.)*

- [ ] **Step 2: Run — expect FAIL** (`COMMAND_CONFIRM_TIMEOUT_SECONDS` missing / no revert):
`./.venv/bin/python -m pytest tests/test_climate.py::test_unconfirmed_command_reverts_and_raises_issue -q`

- [ ] **Step 3: Implement**:
  - `const.py`: add
    ```python
    # How long to trust an optimistic value before the device confirms it. On expiry the
    # entity reverts to the reported state and raises a Repair issue.
    COMMAND_CONFIRM_TIMEOUT_SECONDS: Final = 60
    ```
  - `climate.py` imports: add `from homeassistant.helpers import issue_registry as ir`, `from homeassistant.helpers.event import async_call_later`, and `COMMAND_CONFIRM_TIMEOUT_SECONDS` to the `.const` import. Under TYPE_CHECKING add `from datetime import datetime` and `from homeassistant.core import CALLBACK_TYPE`.
  - Add field `_confirm_unsub: CALLBACK_TYPE | None = None` and an issue-id property:
    ```python
    @property
    def _issue_id(self) -> str:
        return f"command_unconfirmed_{self.coordinator.config_entry.entry_id}"
    ```
  - Replace the Task-2 stubs with:
    ```python
    def _schedule_confirm_timeout(self) -> None:
        self._cancel_confirm_timeout()
        self._confirm_unsub = async_call_later(
            self.hass, COMMAND_CONFIRM_TIMEOUT_SECONDS, self._confirm_timeout
        )

    def _cancel_confirm_timeout(self) -> None:
        if self._confirm_unsub is not None:
            self._confirm_unsub()
            self._confirm_unsub = None

    def _confirm_all(self) -> None:
        """A pending command was confirmed: stop the timer and clear any issue."""
        self._cancel_confirm_timeout()
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)

    @callback
    def _confirm_timeout(self, _now: datetime) -> None:
        """The device never confirmed the command: revert to truth and flag it."""
        self._confirm_unsub = None
        if not self._has_pending():
            return
        self._optimistic_hvac_mode = None
        self._optimistic_target = None
        self._optimistic_preset = None
        self.async_write_ha_state()
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="command_unconfirmed",
        )

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_confirm_timeout()
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        await super().async_will_remove_from_hass()
    ```
  - `strings.json` and `translations/en.json`: add a top-level `"issues"` block (sibling of `"config"`/`"entity"`):
    ```json
    "issues": {
      "command_unconfirmed": {
        "title": "Heater didn't confirm a command",
        "description": "The heater accepted a recent command but its reported state hasn't changed to match, so it may not have applied. The displayed state has been returned to what the heater last reported. Try again, or check the heater."
      }
    }
    ```

- [ ] **Step 4: Run — expect PASS** (add a second test asserting a later *confirmed* command clears the issue: refresh with matching status → `async_get_issue(...) is None`). Then full suite + ruff + format + mypy + codespell.

- [ ] **Step 5: Commit**: `git commit -am "feat: revert + raise a Repair issue when a command is never confirmed"`

---

## Self-review

- **Spec coverage:** §1 hvac_action→None → Task 1. §2 optimistic + reconciliation → Task 2. §3 timeout + revert + Repair issue (mode B) + translations → Task 3. Mode A (no-ack `HomeAssistantError`) is already covered by `_async_guard` + optimistic-after-ack ordering; assert it with the existing `test_command_failure_raises_home_assistant_error` (no new task).
- **Placeholders:** none — all code is concrete. The Task-2 `_schedule_confirm_timeout`/`_confirm_all` stubs are explicitly replaced in Task 3.
- **Type consistency:** `_set_optimistic(hvac_mode=, target=, preset=)`, `_real_hvac_mode()`, `_real_preset_mode()`, `_has_pending()`, `_confirm_all()`, `_confirm_timeout(now)`, `_issue_id`, `COMMAND_CONFIRM_TIMEOUT_SECONDS` are used consistently across tasks.
- **Ambiguity:** `async_turn_on` optimistically shows `HEAT`; if the device resolves to `AUTO` (schedule on), the next echo reconciles it — acceptable and self-correcting.
