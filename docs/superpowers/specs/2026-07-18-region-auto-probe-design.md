# Region discovery — per-device, across all regions (#4)

- **Date:** 2026-07-18
- **Issue:** comfort-hub/delonghi-comfort-ha#4
- **Status:** Approved design — empirically validated against the live backend
- **Scope:** cross-repo — `delonghi-comfort` (library, 0.2.1) then `delonghi-comfort-ha`

## Problem

The config flow hardcodes region `eu`. `_authenticate` builds `DelonghiComfort(session=...)`
with the default region and `_create_entry` stores `CONF_REGION: "eu"`. A non-EU account only
ever queries the EU device-list endpoint, which returns none of its devices, so the flow aborts
with `no_devices` — the integration cannot be added at all. The runtime already honours the
stored region (`coordinator.py` builds the client with `region=config_entry.data[CONF_REGION]`).

Region is really a **per-device** property — which regional backend hosts a given heater's
shadow — not a per-account one. A design that picks a single account region would hide a second
device in another region.

## How region works (library `delonghi-comfort` 0.2.0)

- `DelonghiComfort(session, region="eu"|"us", …)`. `region` selects the REST device-list endpoint
  (`REST_BASE_URLS[region]/devices`) and the IoT/MQTT endpoint.
- **Login is region-agnostic.** `async_login` pool-probes `GIGYA_API_KEYS` (skips `400093`
  "wrong pool", tries the next), so any account logs in. All pools live on `eu1.gigya.com`.
- The REST device-list is authorised by the Gigya JWT via a Lambda authorizer; the JWT is the
  account's global identity, independent of region.

## Empirical validation (live, real backend)

A one-off probe with a real EU account (credentials from `.env`) logged in once, then fetched
devices for both regions with the shared credentials:

```
LOGIN: OK
region=eu: OK -> 1 device(s)
region=us: OK -> 0 device(s)
```

Confirmed: (1) the EU-minted Gigya JWT **is accepted by the US REST endpoint**, and (2) a region
where the account has no devices returns an **empty list — no 401/403, no exception**. So one
login + one JWT can enumerate every region.

## Approach — discovery in the library, per-device region

Region discovery is a library capability (auth + device listing already live there, and the
library owns the region tables). Add a discovery entry point to the library that logs in once and
returns **every device across all supported regions, each tagged with its region**. The HA config
flow consumes that list and stores the chosen device's region — it holds no region mechanics of
its own.

*Alternatives considered:* (a) integration-only auto-probe — rejected: leaks the multi-client /
`refresh_jwt` / region-list mechanics into the config flow and isn't reusable. (b) first-region-
wins — rejected: silently hides a second region's devices. The library approach costs a 0.2.1
release + HA re-pin, which is cheap now that release-please + PyPI trusted publishing are in place.

---

## Design — library (`delonghi-comfort` 0.2.1)

### Public API additions (exported from `delonghi_comfort`)

```python
@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """A device found during discovery, tagged with the region whose backend hosts it."""
    device: Device
    region: str

SUPPORTED_REGIONS: Final[tuple[str, ...]] = ("eu", "us")  # probe order

async def async_discover(
    session: aiohttp.ClientSession, email: str, password: str
) -> tuple[GigyaCredentials, list[DiscoveredDevice]]:
    """Log in once and return every device on the account across all supported regions."""
```

### Behaviour

```python
async def async_discover(session, email, password):
    gigya = GigyaAuth(session)
    credentials = await gigya.login(email, password)   # region-agnostic; AuthenticationError on bad creds
    jwt = await gigya.get_jwt(credentials)              # one JWT, valid cross-region (validated)
    found: list[DiscoveredDevice] = []
    last_error: TransportError | None = None
    for region in SUPPORTED_REGIONS:
        try:
            devices = await async_get_devices(session, jwt, region)  # rest.py module fn
        except TransportError as err:
            last_error = err
            continue
        found.extend(DiscoveredDevice(device=d, region=region) for d in devices)
    if not found and last_error is not None:
        raise last_error
    return credentials, found
```

- `AuthenticationError` (login, or an unexpected 401/403 on a region) propagates — a real auth
  failure, not "no devices here".
- `TransportError` on a region is recorded and the next region is tried; only re-raised if **no**
  region produced devices (so one flaky region can't mask a good one).
- Devices from every region are aggregated, so multi-region accounts get all their devices.

### Library tests (TDD)
Mock `GigyaAuth.login`/`get_jwt` and `rest.async_get_devices`. Cases:
1. devices in `eu` only -> one `DiscoveredDevice`, region `eu`.
2. devices in `us` only -> region `us`.
3. devices in **both** regions -> aggregated list, each tagged correctly.
4. none anywhere -> `(credentials, [])`.
5. bad password -> `AuthenticationError` propagates.
6. one region `TransportError`, other has devices -> returns the good ones (no raise).
7. all regions `TransportError`, none found -> raises `TransportError`.

Release as a `feat:` -> release-please cuts **0.2.1** -> PyPI.

---

## Design — HA integration (after 0.2.1 is published)

### Pin bump
`manifest.json` `requirements: ["delonghi-comfort==0.2.1"]`; `pyproject.toml`
`delonghi-comfort>=0.2.1`.

### config_flow.py
`async_step_user` calls the library discovery and branches on the tagged list:

```python
credentials, discovered = await async_discover(session, email, password)
# discovered: list[DiscoveredDevice]
if not discovered:                      -> errors["base"] = "no_devices"
elif len(discovered) == 1:              -> _create_entry(discovered[0])
else:                                   -> async_step_device (pick one)
```

- `_create_entry(discovered: DiscoveredDevice)` stores `CONF_REGION: discovered.region` (plus the
  existing device fields from `discovered.device`).
- `async_step_device` lists all discovered devices. The label shows the region **only when it
  disambiguates** — i.e. when the set has more than one distinct region:
  `f"{d.device.model} ({d.device.serial_number})"` + ` — {d.region.upper()}` when multi-region.
  Dynamic label text only; **no new translation strings**.
- reauth (`async_step_reauth_confirm`) re-authenticates with the entry's stored region
  (`DelonghiComfort(session, region=reauth_entry.data[CONF_REGION]).async_login(...)`); it does not
  re-discover.

### Error mapping (existing keys — no new strings)
- `async_discover` `AuthenticationError` -> `invalid_auth`.
- `async_discover` `TransportError` -> `cannot_connect`.
- empty `discovered` -> `no_devices`.

### HA tests (TDD — `tests/test_config_flow.py`)
Mock `async_discover`. Cases:
1. single device (eu) -> entry `CONF_REGION == "eu"`.
2. single device (us) -> entry `CONF_REGION == "us"`.
3. multiple devices, same region -> device-select; labels omit region.
4. multiple devices, **different** regions -> device-select; labels include region; chosen device's
   region stored.
5. no devices -> `no_devices`.
6. bad password (`AuthenticationError`) -> `invalid_auth`.
7. `TransportError` -> `cannot_connect`.
8. reauth uses the entry's stored region.

Existing config-flow tests that mock `DelonghiComfort.async_login`/`async_get_devices` are updated
to mock `async_discover`.

---

## Sequencing (cross-repo)
1. **Library:** implement `async_discover` + `DiscoveredDevice` + `SUPPORTED_REGIONS` + tests (TDD),
   merge as `feat:` -> release-please cuts **0.2.1** -> PyPI.
2. **HA:** re-pin `delonghi-comfort==0.2.1`, rewrite the config-flow discovery + tests, merge.
   Cut a HA release afterward.

## Out of scope
- Changing region on an existing entry (reconfigure) — belongs to quality-scale #12.
- Existing `eu` entries — no migration needed; they remain correct.
- Gigya datacenter selection — all pools are on `eu1`.

## Risks
- One extra REST call at setup (both regions are always queried instead of short-circuiting) — a
  one-time, setup-only cost; negligible.
- The multi-region path is unverified on real hardware (we have one EU device). The per-region
  fetch is the exact validated call, just run for each region, so the risk is low; the design
  degrades gracefully (a failing region can't hide a good one).
