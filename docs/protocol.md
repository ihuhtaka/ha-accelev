# Accelev / EVTUN Cloud API Protocol

Reverse-engineered protocol reference for the Accelev EV charger cloud API.

Sources:
- Vendor document "Accelev API v0.14 (24.03.2022)" — contains typos; where it conflicts
  with the observed behavior below, **observed behavior wins**.
- A Node-RED flow that polled this API every 60 s for ~2 years without issues.

> ⚠ **Verification status:** core behavior verified against the live API on
> 2026-08-26 (sanitized captures in `docs/samples/`). Two doc-vs-reality
> differences found: `info` returns a **multi-line** response (see samples),
> and rejected credentials yield **HTTP 200 + empty body**, not an error
> message.

## Endpoint

```
GET http://server.evtun.com:8091/api.php?charger={CHARGER_ID}&pin={PIN}&{command}
```

- Plain HTTP, no session or handshake; credentials are query params on **every** request.
- `CHARGER_ID` looks like `FA0123456` (printed in the vendor app / charger label).
- Multiple commands per request are supported (`start=true&current=6`) but the
  integration deliberately keeps one concern per call.

## Read commands

| Command | Response body (plain text) | Meaning |
|---|---|---|
| `info` | multi-line: `FA0123456`␍␊`Total energy is 99.4 kWh`␍␊`Overall SOP is  1.3`␍␊`Firmware ver is 2.73` | serial, **lifetime** energy (kWh), SOP, firmware |
| `whatisvoltage=ask` | bare float, e.g. `230.4` | actual voltage (V) |
| `whatiscurrent=ask` | bare float | **actual** current to car (A) — not the setpoint |
| `whatisenergy=ask` | bare float | **session** energy (kWh) — resets at the start of each charge |
| `whatispower=ask` | bare float | actual power (**kW**) |
| `whatislasttime=ask` | `HH:MM:SS` | charger-local time when the values above were recorded |

Notes:
- Vendor doc spells the last command `whatislastitme` — that is a typo; `whatislasttime` is
  what the working system used.
- Parsers should extract the **first float** from the body (tolerates both `230.4` and
  `Voltage is 230.4 V` styles, and comma decimal separators).
- Proven poll cadence: all five `whatis*` every 60 s + `info` every 300 s.

## Write commands

| Command | Success response | Notes |
|---|---|---|
| `current={amps}&ack=1` | `1` | set charge current; vendor doc: valid 6–32 A, decimals allowed (`6.5`). Values outside range: "no action done" |
| `start=true&ack=1` | `1` | start charging; value `true` is obligatory |
| `stop=true&ack=1` | `1` | stop charging; value `true` is obligatory |
| `gridm=on\|off&ack=1` | `1` | grid monitoring on/off |
| `batcare=on\|off&ack=1` | `1` | BatteryCare on/off |
| `nofull=on\|off&ack=1` | `1` | "no full charging" on/off |
| `settime=HHMM&ack=1` | `1` | set charger clock, 4 chars zero-padded (`0642` = 06:42) |

`ack=1` requests an acknowledgement. Vendor doc: `1` = applied, `0` = rejected.
**Verified live (2026-08-26):** multi-command requests return **one digit per
command** — e.g. `current=12&ack=1` returns `11`. Integration rule: success =
non-empty body consisting only of `1` digits.

## Live-observed behavior (verified 2026-08-26, firmware 2.73)

- **Upload cadence while charging: ~1/minute** (`whatislasttime` advances
  ~60 s per minute). While idle-online, fresh zero readings keep coming too.
- **After `stop=true`, the charger stops uploading entirely.** The server
  keeps serving the last snapshot *indefinitely* — `whatiscurrent` kept
  returning a phantom `5.9` for 2+ hours while `whatisenergy` and
  `whatislasttime` stayed frozen. **Freshness detection: treat data as stale
  when `whatislasttime` hasn't advanced for > 3 minutes** (3 missed uploads).
  This explains the old bridge's "force values to 0 when not charging" hack —
  it was masking exactly this.
- **`stop=true` is flaky**: a single stop is often ignored by the charger.
  Proven recipe (from years of production use): send stop **5 times, ~1 s
  apart**. `start=true` works with a single send.
- Set-current takes effect within ~60 s; the car then ramps to it.
- New charge session resets `whatisenergy` to ~0 (session counter).
- Charger clock runs its own timezone/offset — never compare `whatislasttime`
  against wall-clock time; only use change detection.

State of `gridm`/`batcare`/`nofull` is **not readable** via the API — integrations must
track it optimistically.

## Error behavior (verified 2026-08-26)

| Situation | Observed |
|---|---|
| Bad pin / unknown charger | **HTTP 200, empty body** — no error message. Detect via empty response |
| Server down / unreachable | TCP connect timeout (observed during the 2026-08-26 outage: host pinged, ports 80/443/8091 closed; recovered later the same day) |
| Value query while idle | bare `0` (integer), not empty |
| HTTP errors | not observed; status ≥ 400 treated as connection error |

The integration treats an empty `info` body as an auth failure in the config
flow (`invalid_auth`), but as a transient failure during polling (an offline
charger may look identical, and this avoids false reauth prompts).

## Security note

`charger` + `pin` are the only credentials and are sent in cleartext over HTTP.
Never commit real values — samples in this repo use `FA000000` / `000000`.
