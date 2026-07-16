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

- **Climate** — on/off, target temperature, measured room temperature.
- **Switches** — Eco, Night mode, Silent, Child lock.
- **Number** — LED ring brightness (0–3).
- **Sensors** — room temperature, power-board / display-board temperatures (diagnostic).
- **Binary sensor** — fault/alarm (with the individual active flags as attributes).

For driving the heater from an external room thermostat (e.g. Versatile Thermostat) with
minimal cycling and no relay noise, see [`docs/control-tuning.md`](docs/control-tuning.md).

## Installation (HACS)

1. HACS → Integrations → ⋮ → **Custom repositories**.
2. Add `https://github.com/comfort-hub/delonghi-comfort-ha` as an **Integration**.
3. Install **De'Longhi Comfort**, then restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → De'Longhi Comfort**.
5. Sign in with your My Comfort Hub email + password. The password is not stored — only a
   long-lived Gigya session token, refreshed automatically (with a reauth prompt if revoked).

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
uv sync
uv run pytest
uv run ruff check
uv run mypy custom_components
```

The `delonghi-comfort` library is consumed from the sibling checkout during development (see
`[tool.uv.sources]` in `pyproject.toml`).

## License

GPL-3.0-or-later.
