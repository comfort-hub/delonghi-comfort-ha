# Local (LAN) control investigation

**Question:** can a De'Longhi "My Comfort Hub" heater (e.g. the Dragon 5 Connect,
`TRD51024WIFI.G`) be controlled locally — over the LAN, without De'Longhi's cloud?

**Answer:** no. The `/ws/lan2lan` LAN WebSocket exists in the firmware but is **disabled
for the heater line** at both the app and firmware level. Every non-physical avenue was
tested and closed. This integration therefore uses De'Longhi's cloud (AWS IoT), which works
both at home and away.

This document records the investigation so nobody has to repeat it.

---

## Background — why local control looked plausible

The heaters run De'Longhi's "Daedalus" stack: **Gigya** (SAP CDC) for login and **AWS IoT**
for the device. A community integration for De'Longhi **coffee machines**,
[`sk7n4k3d/delonghi-daedalus-ha`](https://github.com/sk7n4k3d/delonghi-daedalus-ha), controls
them entirely over a LAN WebSocket:

```
wss://<device-ip>/ws/lan2lan        (TLS, self-signed, trust-all on the client)
first frame: {"Message":"AUTH","SerialNo":"<serial>","AuthToken":"<Gigya JWT>"}
on success:  {"Response":"OK","ConnectionId":<int>}
```

The wire code lives in a **shared** `appliance_kit.web_socket` module that the heater app also
bundles — so the heater *might* expose the same server. It does. It just refuses to talk.

---

## What we found

### 1. The heater serves `/ws/lan2lan` but rejects every request

- The only open TCP port is **443**; it serves the WebSocket at `/ws/lan2lan` and 404s
  everything else.
- Sending the exact coffee-machine AUTH frame — with a **valid, cloud-accepted** Gigya JWT and
  the device's **own** serial — returns `{"Message":"AUTH","Response":"UNAUTHORIZED"}`.
- An error-taxonomy probe (valid / empty / garbage / bad-signature / missing token × every
  serial variant × extra fields like `ApiKey`/`Pool`/`Bearer`) returned the **byte-identical**
  `UNAUTHORIZED` for all 17 permutations — including frames with *no token field* and *no serial
  field*. A real credential check fails malformed frames differently; uniform rejection means the
  handler refuses `lan2lan` **regardless of input**.
- Any other message type (`HELLO`, `PING`, `GetStatus`, `SUBSCRIBE`, …) likewise returns
  `{"Message":<echoed>,"Response":"UNAUTHORIZED"}`: the handler is functional and gates every
  message behind an authentication that, for the heater, never succeeds.

### 2. Decompilation — the app disables LAN for heaters

Decompiling the Android app (Flutter front-end over a Java/Kotlin `appliance_kit` SDK) shows the
LAN path is gated by a boolean:

```java
// AWSCloudApplianceConnection.initWebSocketConnection(String token, boolean lan2lanEnabled)
if (!lan2lanEnabled) {
    log("LAN-to-LAN is disabled by configuration.");
    return;                 // the LAN socket is never created
}
```

- `lan2lanEnabled` is decided in the Flutter layer and passed down through the Pigeon bridge.
- It has **no per-device cloud source**: the REST device model and the `MachineCapabilities`
  shadow carry no `lan2lan` field, so it is not a toggle we can flip via the API.
- The native AUTH frame construction (`WebSocketClient.sendAuth`) is byte-identical to what we
  sent, and the JWT it uses is the same Gigya token used for the cloud MQTT connection.

The coffee firmware + app enable `lan2lan`; the heater app ships the same SDK code with the flag
**off**.

### 3. Honeypot — the app never even tries

The app uses a trust-all `X509TrustManager` for `/ws/lan2lan`, so it accepts any certificate. We
stood up a trust-all WSS server in the heater's place and drove the heater from the **official
app**: it **never opened `/ws/lan2lan`**. This confirms `lan2lanEnabled = false` for the heater
empirically — there is no captured "good" handshake to replay, because the app makes none.

### 4. Attack-surface recon — nothing else is exposed

A gentle port scan (ESP32s have tiny TCP stacks — high concurrency makes them drop every
connection and look closed) found **only port 443**:

- TLS cert = the device's **AWS IoT certificate** (`CN=AWS IoT Certificate`, issuer Amazon).
- HTTP returns **404 for every path** (`/`, `/status`, `/info`, `/prov-*`, `/config`, …).
- `/ws/lan2lan` is the **only** WebSocket route; all others 404.
- No provisioning endpoints are reachable during normal operation.

### 5. SoftAP / BLE provisioning — only sets Wi-Fi

The device supports Espressif **unified provisioning** (SoftAP/BLE) when factory-reset. The app's
provisioning code (`EspPairableAppliance`) does exactly two things:

- `provision(ssid, passphrase)` → the stock Espressif `espDevice.provision()` call, sending
  **only** the target Wi-Fi credentials.
- `getMachineId()` → sends the bytes `"echo"` to a `custom-data` protocomm endpoint; the device
  **echoes back its baked-in machineId** (the AWS IoT thing name).

So provisioning **reads** the device's identity and **sets** its Wi-Fi — it cannot change the
broker, thing name, or certificate. The identity is baked into flash at manufacture.
Re-provisioning the heater ourselves would only move it to a different Wi-Fi; it would still
connect out to De'Longhi's AWS IoT.

### 6. Cloud redirect — the firmware pins the CA

The last non-destructive idea: make the heater talk to **our** MQTT broker instead of De'Longhi's,
then drive it with the (already reverse-engineered) shadow + `commands/request` protocol. We
pointed the AWS IoT broker hostname at a local machine via a DNS rewrite and stood up a TLS
listener there. The heater **connected**, then **aborted the TLS handshake with `unknown_ca`**:

```
TCP connect on :8883 from <heater>
TLS handshake FAILED: TLSV1_ALERT_UNKNOWN_CA
```

The firmware validates the broker's server certificate against a **pinned root CA** (Amazon Root
CA) — standard `esp-aws-iot` behaviour. We cannot impersonate the broker without a certificate
chaining to that CA, which we cannot forge. Redirect is not viable.

---

## What local control would require

The only remaining avenue is **physical**: UART/JTAG into the ESP32 and modify the flash — e.g.
replace the trusted CA (or repoint the broker) and combine with the DNS redirect above. This is
gated by whether **secure boot + flash encryption** efuses are set. If they are (typical for a
production mains appliance) the flash is neither readable nor modifiable, and even the hardware
route is closed.

Reflashing fully custom firmware (ESPHome/Tasmota) is **not advisable**: it would discard
De'Longhi's heating-element control, thermal cutoffs, and tip-over safety logic on a ~2 kW mains
appliance.

---

## Conclusion

Local control is closed for this heater **by design**, at both the app and firmware level. The
cloud path — Gigya JWT → AWS IoT MQTT shadow reads + a `commands/request`/`commands/response`
topic pair — is the intended and fully functional channel, and is what this integration and the
[`delonghi-comfort`](https://github.com/comfort-hub/delonghi-comfort) library use. It works on the
local network and remotely.
