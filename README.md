# De'Longhi Comfort — Home Assistant integration

Control De'Longhi **"My Comfort Hub"** connected heaters (e.g. the **Dragon 5 Connect**,
`TRD51024WIFI.G`) from Home Assistant, over De'Longhi's cloud — locally *and* remotely, the
same way the official app does.

It uses a proper `DataUpdateCoordinator` with a live push connection (AWS IoT MQTT shadow),
`config_flow` with re-authentication, and is built on the
[`delonghi-comfort`](https://github.com/comfort-hub/delonghi-comfort) library.

> ⚠️ Unofficial. Built by reverse-engineering the public app for interoperability with
> hardware you own. Not affiliated with or endorsed by De'Longhi.

## Entities

- **Climate** — power (off / heat / auto), target temperature, measured room temperature. It also carries an **Eco** preset (the heater's power-limit mode). *Auto*
  follows the heater's on-board weekly schedule, so the setpoint is read-only there. The heater does not report whether its element is
  heating, so no heating/idle action is shown.
- **Switches** *(config)* — Night mode, Silent, Child lock.
- **Select** *(config)* — LED display brightness (Off / Low / Medium / High).
- **Sensors** — room temperature and timer remaining; plus diagnostics that are **disabled by
  default**: power-board / display-board temperatures, LAN IP, firmware partition, update progress.
- **Binary sensors** — Safety cut-out, Overheat protection and Malfunction (diagnostic faults);
  Timer running; and Cloud connection (whether the live push link is up).

For driving the heater from an external room thermostat (e.g. Versatile Thermostat) with
minimal cycling and no relay noise, see [`docs/control-tuning.md`](docs/control-tuning.md).

## Supported devices

My Comfort Hub heaters. Tested on the Dragon 5 Connect `TRD51024WIFI.G`.

## Installation (HACS)

1. HACS → search **De'Longhi Comfort** → **Download**, then restart Home Assistant.
2. **Settings → Devices & Services → Add Integration → De'Longhi Comfort**.
3. Sign in with your My Comfort Hub email + password. The password is not stored — only a
   long-lived Gigya session token, refreshed automatically (with a reauth prompt if revoked).

## How data updates

State arrives by live MQTT push, plus a 60 s poll that also checks the heater is online.

## Known limitations

- Cloud-only: there is no local control path (see below).
- The setpoint is read-only in **Auto**.
- The °F range is 41–82.
- Telemetry is sparse while the heater is off (see the **Last reported** sensor).
- No heating/idle action.
- If the heater does not confirm a command, a Repair issue is raised.

## Use cases

- Schedules driven from Home Assistant automations.
- Presence-based heating.
- Control from an external thermostat — see [`docs/control-tuning.md`](docs/control-tuning.md).

## Troubleshooting

- Entities unavailable: the heater is offline in the De'Longhi app.
- A reauth prompt means your password changed; re-enter it.
- Download diagnostics from the device page when reporting a problem.
- Enable debug logging:

  ```yaml
  logger:
    logs:
      custom_components.delonghi_comfort: debug
      delonghi_comfort: debug
  ```

## Removal

**Settings → Devices & Services → De'Longhi Comfort → ⋮ → Delete**. Then remove it in HACS and
restart Home Assistant.

## Why cloud, not local?

The heater exposes a `/ws/lan2lan` LAN WebSocket (the same one De'Longhi's coffee machines use
for local control), but on the heater line it is **disabled by design** — the app never opens it
and the firmware rejects every request. We investigated this thoroughly (decompilation, protocol
probing, a honeypot, and a cloud-broker redirect) and confirmed there is no local control path
short of physically modifying the device. The full write-up is in
[`docs/local-control-investigation.md`](docs/local-control-investigation.md).

So this integration uses the cloud path, which is fully functional both at home and away.

## Development

```bash
uv sync --locked
uv run pytest
uv run ruff check
uv run mypy custom_components
```

`uv.lock` is committed and CI installs against it with `uv sync --locked`. The `delonghi-comfort`
library is resolved from PyPI (pinned in `manifest.json`), so no sibling checkout is required — run
`uv lock` after changing dependencies and commit the refreshed lockfile.

## License

GPL-3.0-or-later.
