# Region Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Discover a De'Longhi account's devices across all supported regions and let non-EU (and multi-region) accounts add the Home Assistant integration.

**Architecture:** Add an `async_discover` entry point to the `delonghi-comfort` library (0.2.1) that logs in once and returns every device across all regions, each tagged with its region. The HA config flow consumes that tagged list and stores the chosen device's region; it holds no region logic itself.

**Tech Stack:** Python 3.12+/3.13, aiohttp, `delonghi-comfort` library, Home Assistant config flow, pytest / pytest-homeassistant-custom-component, uv, Ruff, mypy.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-18-region-auto-probe-design.md`.
- **HA style:** Ruff-clean, PEP8/257; f-strings (not `%`/`format`) except `%`-style logging; ordered imports; constants alphabetical/grouped with the region tables; comments are full sentences ending in a period; typing throughout; no secrets in logs.
- Library `async_discover` return type is fixed: `tuple[GigyaCredentials, list[DiscoveredDevice]]`, `DiscoveredDevice(device: Device, region: str)`.
- Regions: `SUPPORTED_REGIONS = ("eu", "us")`, eu first.
- Cross-repo order: library 0.2.1 published to PyPI **before** the HA pin bump.
- Reuse the existing library fake transports (`tests/fakes.py`: `FakeResponse`, `make_session`) and the HA `mock_*` fixtures (`tests/conftest.py`); do not introduce a new mocking style.

---

## Phase 1 — Library (`delonghi-comfort`, cut 0.2.1)

Work in `/home/shaunes/dev/oss/comfort-hub/delonghi-comfort` on a branch `feat/region-discovery`.

### Task L1: `async_discover` + `DiscoveredDevice` + `SUPPORTED_REGIONS`

**Files:**
- Modify: `delonghi_comfort/const.py` (add `SUPPORTED_REGIONS` beside the region tables)
- Create: `delonghi_comfort/discovery.py`
- Modify: `delonghi_comfort/__init__.py` (export the three names)
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `GigyaAuth` (`.gigya`), `async_get_devices` (`.rest`), `TransportError` (`.exceptions`), `REST_BASE_URLS` keys (`.const`), `Device` (`.models`).
- Produces:
  - `SUPPORTED_REGIONS: Final[tuple[str, ...]] = ("eu", "us")`
  - `DiscoveredDevice(device: Device, region: str)` — frozen dataclass
  - `async def async_discover(session, email, password) -> tuple[GigyaCredentials, list[DiscoveredDevice]]`

- [ ] **Step 1: Add the constant.** In `const.py`, immediately after the `IOT_ENDPOINTS` table:

```python
# Regions to search during discovery (probe order; eu first — most accounts).
SUPPORTED_REGIONS: Final[tuple[str, ...]] = ("eu", "us")
```

- [ ] **Step 2: Write the failing tests** — `tests/test_discovery.py`:

```python
"""Tests for cross-region device discovery."""

from __future__ import annotations

import base64

import pytest

from delonghi_comfort import DiscoveredDevice, async_discover
from delonghi_comfort.exceptions import AuthenticationError, TransportError

from .fakes import FakeResponse, make_session

_SECRET = base64.b64encode(b"secret").decode()


def _gigya_routes() -> dict[str, FakeResponse]:
    return {
        "accounts.login": FakeResponse(
            json_data={
                "errorCode": 0,
                "sessionInfo": {"sessionToken": "st", "sessionSecret": _SECRET},
            }
        ),
        "accounts.getJWT": FakeResponse(json_data={"id_token": "jwt"}),
    }


def _devices(*names: str) -> FakeResponse:
    return FakeResponse(
        json_data={"ownedByMe": [{"machineName": n, "status": "ONLINE"} for n in names]}
    )


async def test_discover_eu_only() -> None:
    """A device only in eu is returned tagged with region eu."""
    session = make_session(
        {**_gigya_routes(), "eu-central-1": _devices("EU1"), "us-east-1": _devices()}
    )
    credentials, found = await async_discover(session, "me@example.com", "pw")
    assert credentials.session_token == "st"
    assert [(d.device.thing_name, d.region) for d in found] == [("EU1", "eu")]


async def test_discover_us_only() -> None:
    """A device only in us is returned tagged with region us."""
    session = make_session(
        {**_gigya_routes(), "eu-central-1": _devices(), "us-east-1": _devices("US1")}
    )
    _, found = await async_discover(session, "me@example.com", "pw")
    assert [(d.device.thing_name, d.region) for d in found] == [("US1", "us")]


async def test_discover_aggregates_both_regions() -> None:
    """Devices in both regions are aggregated, each tagged correctly."""
    session = make_session(
        {**_gigya_routes(), "eu-central-1": _devices("EU1"), "us-east-1": _devices("US1")}
    )
    _, found = await async_discover(session, "me@example.com", "pw")
    assert {(d.device.thing_name, d.region) for d in found} == {("EU1", "eu"), ("US1", "us")}


async def test_discover_none_returns_empty() -> None:
    """No devices anywhere returns credentials and an empty list."""
    session = make_session(
        {**_gigya_routes(), "eu-central-1": _devices(), "us-east-1": _devices()}
    )
    credentials, found = await async_discover(session, "me@example.com", "pw")
    assert credentials.session_token == "st"
    assert found == []


async def test_discover_bad_password_raises_auth() -> None:
    """A rejected login propagates AuthenticationError."""
    session = make_session(
        {"accounts.login": FakeResponse(json_data={"errorCode": 403042})}
    )
    with pytest.raises(AuthenticationError):
        await async_discover(session, "me@example.com", "wrong")


async def test_discover_skips_a_transient_region() -> None:
    """A region that errors transiently is skipped when another has devices."""
    session = make_session(
        {
            **_gigya_routes(),
            "eu-central-1": FakeResponse(status=502, text_data="bad gateway"),
            "us-east-1": _devices("US1"),
        }
    )
    _, found = await async_discover(session, "me@example.com", "pw")
    assert [(d.device.thing_name, d.region) for d in found] == [("US1", "us")]


async def test_discover_all_regions_failing_raises() -> None:
    """If every region errors and none have devices, the error is raised."""
    session = make_session(
        {
            **_gigya_routes(),
            "eu-central-1": FakeResponse(status=502, text_data="bad gateway"),
            "us-east-1": FakeResponse(status=503, text_data="unavailable"),
        }
    )
    with pytest.raises(TransportError):
        await async_discover(session, "me@example.com", "pw")
```

- [ ] **Step 3: Run to verify failure.** `uv run pytest tests/test_discovery.py -q` → FAIL (`ImportError: cannot import name 'async_discover'`).

- [ ] **Step 4: Implement** `delonghi_comfort/discovery.py`:

```python
"""Account-wide device discovery across all supported regions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .const import SUPPORTED_REGIONS
from .exceptions import TransportError
from .gigya import GigyaAuth
from .rest import async_get_devices

if TYPE_CHECKING:
    import aiohttp

    from .gigya import GigyaCredentials
    from .models import Device


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """A device found during discovery, tagged with the region that hosts it."""

    device: Device
    region: str


async def async_discover(
    session: aiohttp.ClientSession, email: str, password: str
) -> tuple[GigyaCredentials, list[DiscoveredDevice]]:
    """Log in once and return every device on the account across all regions.

    A single Gigya login (which itself probes every account pool) and a single
    JWT are enough to enumerate every region: the JWT is the account's global
    identity and is accepted by each regional device endpoint.

    Args:
        session: Shared aiohttp session.
        email: Account email address.
        password: Account password.

    Returns:
        The Gigya session credentials and every discovered device, each tagged
        with the region whose backend hosts it.

    Raises:
        AuthenticationError: The credentials were rejected.
        TransportError: Every region's device request failed and none returned
            devices.
    """
    gigya = GigyaAuth(session)
    credentials = await gigya.login(email, password)
    jwt = await gigya.get_jwt(credentials)
    found: list[DiscoveredDevice] = []
    last_error: TransportError | None = None
    for region in SUPPORTED_REGIONS:
        try:
            devices = await async_get_devices(session, jwt, region)
        except TransportError as err:
            last_error = err
            continue
        found.extend(DiscoveredDevice(device=device, region=region) for device in devices)
    if not found and last_error is not None:
        raise last_error
    return credentials, found
```

- [ ] **Step 5: Export the names.** In `__init__.py`, add `async_discover`, `DiscoveredDevice`, `SUPPORTED_REGIONS` to the imports and `__all__` (keep `__all__` alphabetical).

- [ ] **Step 6: Run tests.** `uv run pytest tests/test_discovery.py -q` → 7 PASS. Then `uv run pytest -q` (full suite) and `uvx prek run --all-files` → all green.

- [ ] **Step 7: Commit.** `git commit -m "feat: add async_discover for cross-region device discovery"` (note: pre-1.0 the library's `bump-patch-for-minor-pre-major` config releases a `feat` as a **patch** — so this cuts 0.2.1, not 0.3.0).

### Phase-1 gate: release 0.2.1
Open a PR to `main`, merge with the `feat:` subject, let release-please cut **0.2.1**, merge the release PR, confirm PyPI shows `delonghi-comfort 0.2.1`.

---

## Phase 2 — HA integration (`delonghi-comfort-ha`)

Work on the existing branch `fix/region-auto-probe`. Do NOT start until `delonghi-comfort==0.2.1` is on PyPI.

### Task H1: Pin the library to 0.2.1

**Files:** `custom_components/delonghi_comfort/manifest.json`, `pyproject.toml`

- [ ] **Step 1:** `manifest.json` → `"requirements": ["delonghi-comfort==0.2.1"]`.
- [ ] **Step 2:** `pyproject.toml` → `"delonghi-comfort>=0.2.1"`.
- [ ] **Step 3:** `uv lock && uv run --locked python -c "import delonghi_comfort; print(delonghi_comfort.async_discover)"` → prints the function (0.2.1 resolved). Commit `build: require delonghi-comfort 0.2.1`.

### Task H2: Rewrite the config flow around `async_discover`

**Files:**
- Modify: `custom_components/delonghi_comfort/config_flow.py`
- Modify: `tests/test_config_flow.py`, `tests/conftest.py` (fixture mocks `async_discover`)

**Interfaces:**
- Consumes: `async_discover`, `DiscoveredDevice` (from `delonghi_comfort`).
- Produces: config entries whose `CONF_REGION` is the chosen device's region.

- [ ] **Step 1: Update the fixture.** In `tests/conftest.py`, replace the `mock_client`-based login/get_devices mocking with a patch of `custom_components.delonghi_comfort.config_flow.async_discover` (an `AsyncMock`) that returns `(credentials, [DiscoveredDevice(device=THING_DEVICE, region="eu")])` by default. Keep the reauth path mocking `DelonghiComfort.async_login`.

- [ ] **Step 2: Write/adjust the failing tests** in `tests/test_config_flow.py`:
  - `test_user_flow_single_device` → assert `result["data"][CONF_REGION] == "eu"`.
  - `test_user_flow_single_device_us` → discover returns one device region `us`; assert entry `CONF_REGION == "us"`.
  - `test_user_flow_multi_same_region` → two devices both `eu`; device step labels are `"model (serial)"` (no region suffix).
  - `test_user_flow_multi_cross_region` → one `eu`, one `us`; device-step labels include ` — EU`/` — US`; choosing the `us` one stores `CONF_REGION == "us"`.
  - `test_user_flow_no_devices` → discover returns `(creds, [])` → `errors == {"base": "no_devices"}`.
  - `test_user_flow_invalid_auth` → discover raises `AuthenticationError` → `invalid_auth`.
  - `test_user_flow_cannot_connect` → discover raises `TransportError` → `cannot_connect`.
  - reauth test → unchanged behaviour, still succeeds.

- [ ] **Step 3: Run to verify failure.** `uv run pytest tests/test_config_flow.py -q` → FAIL.

- [ ] **Step 4: Implement the config-flow changes:**
  - Import `async_discover, DiscoveredDevice` from `delonghi_comfort`; drop the now-unused `DelonghiComfort`/`Device` imports if reauth no longer needs them (reauth keeps `DelonghiComfort`).
  - Replace `_authenticate` with `_discover(email, password) -> tuple[GigyaCredentials, list[DiscoveredDevice]]` that calls `async_discover`.
  - `async_step_user`: call `_discover`; store `self._discovered: list[DiscoveredDevice]`; branch `not discovered → no_devices`, `len == 1 → _create_entry(discovered[0])`, else `async_step_device`.
  - `async_step_device`: build options from `self._discovered`; include ` — {region.upper()}` in the label only when `len({d.region for d in self._discovered}) > 1`; value is `d.device.thing_name`.
  - `_create_entry(discovered: DiscoveredDevice)`: store `CONF_REGION: discovered.region` and the device fields from `discovered.device`.
  - `async_step_reauth_confirm`: build the client with `region=reauth_entry.data[CONF_REGION]` for `async_login` (region-agnostic but future-proof); no discovery.

- [ ] **Step 5: Run tests.** `uv run pytest -q` → all pass; `uvx prek run --all-files` → green; hassfest/validate clean locally if runnable.

- [ ] **Step 6: Commit.** `git commit -m "fix: auto-discover the account region across all regions (#4)"`.

### Phase-2 gate: HA release
Open the PR (branch already tracks `fix/region-auto-probe`), merge with the `fix:` subject, let release-please cut the HA release, merge the release PR.

---

## Self-Review
- **Spec coverage:** library `async_discover`/`DiscoveredDevice`/`SUPPORTED_REGIONS` (L1) ✓; per-device region + aggregation (L1 + H2) ✓; HA consumes discovery, per-device region stored, multi-region label (H2) ✓; error mapping (H2 tests) ✓; pin bump (H1) ✓; sequencing (phase gates) ✓; reauth stored-region (H2 step 4) ✓.
- **Placeholder scan:** none — all steps carry concrete code or exact commands.
- **Type consistency:** `async_discover -> tuple[GigyaCredentials, list[DiscoveredDevice]]` and `DiscoveredDevice(device, region)` used identically in L1 and H2.
