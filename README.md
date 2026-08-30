# Accelev EV Charger — Home Assistant integration

[![hassfest](https://github.com/ihuhtaka/ha-accelev/actions/workflows/validate.yml/badge.svg)](https://github.com/ihuhtaka/ha-accelev/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

A custom [Home Assistant](https://www.home-assistant.io/) integration for
**Accelev** portable EV chargers, using the vendor's cloud API
(`server.evtun.com`, documented in [docs/protocol.md](docs/protocol.md)).

> ⚠️ **Disclaimer:** This is an unofficial, community-made integration. It is
> not affiliated with or endorsed by EVTUN / Accelev. It depends on the
> vendor's cloud service — if that service is down or changes, the
> integration stops working. Use at your own risk.

## Features

- **Sensors:** voltage, current, power, session energy (per charge),
  total/lifetime energy (Energy-dashboard ready, `total_increasing`),
  charger info, last charger report time.
- **Binary sensors:** charging (derived from actual current, with an
  energy-delta fallback), server online (cloud API reachability).
- **Controls:** charge start/stop switch, charging current number
  (6–24 A, 0.5 A steps), grid monitoring / BatteryCare / no-full-charging
  switches, sync-charger-time button.
- Config flow — no YAML, credentials are validated on setup.
- Polls the cloud API every 60 s (configurable, 30–600 s).

## Installation

### HACS (recommended)

1. HACS → **Integrations** → ⋮ → **Custom repositories**.
2. Add `https://github.com/ihuhtaka/ha-accelev` with category
   **Integration**.
3. Install **Accelev EV Charger**, restart Home Assistant.

### Manual

1. Copy `custom_components/accelev/` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

**Settings → Devices & Services → Add Integration → "Accelev EV Charger"**

| Field | Where to find it |
|---|---|
| Charger ID | Charger label / vendor app, e.g. `FA0123456` |
| PIN | 6-digit PIN from the vendor app |

The poll interval (default 60 s) can be changed later via the integration's
**Configure** button.

## Entities

One device **Accelev {charger ID}** with:

| Entity | Notes |
|---|---|
| `sensor.*_voltage` | V |
| `sensor.*_current` | A — actual current to the car, not the setpoint |
| `sensor.*_power` | kW native, displays as W by default |
| `sensor.*_session_energy` | kWh, resets at the start of each charge |
| `sensor.*_total_energy` | kWh, lifetime — use this on the Energy dashboard |
| `sensor.*_charger_info` | Raw info string; SOP/firmware as attributes (diagnostic) |
| `sensor.*_last_charger_report` | `HH:MM:SS` charger-local (diagnostic) |
| `binary_sensor.*_charging` | On when current > 0.3 A or session energy is rising |
| `binary_sensor.*_server_online` | Off = vendor cloud unreachable (diagnostic) |
| `switch.*_charge` | Start/stop charging; state reflects actual charging |
| `switch.*_grid_monitoring` | Optimistic (state not readable from the API) |
| `switch.*_battery_care` | Optimistic |
| `switch.*_no_full_charging` | Optimistic |
| `number.*_charging_current` | 6–24 A, step 0.5 A; restored after restart |
| `button.*_sync_charger_time` | Sets the charger clock to HA's local time |

## Troubleshooting

- **"Could not reach the Accelev cloud API" during setup** — the vendor server
  is down or your network blocks outbound port 8091. Check the
  `binary_sensor.*_server_online` entity of an existing entry, or try
  `curl "http://server.evtun.com:8091/api.php?charger=YOUR_ID&pin=YOUR_PIN&info"`.
- **Entities unavailable** — two consecutive failed polls mark entities
  unavailable; a single transient failure keeps the previous values.
- **Grid monitoring / BatteryCare / no-full switches show wrong state** — the
  API cannot report these states, so the integration tracks them
  optimistically. Toggle once to sync reality with the display.
- **Charge switch lags reality by a few minutes** — after a stop, the charger
  stops uploading and the API keeps serving phantom readings (verified: a
  phantom 5.9 A for 2+ hours). The integration detects staleness via the
  last-report timestamp (>3 min frozen ⇒ current/power read 0, charging off)
  and the switch shows your intent immediately while truth catches up.
  Related firmware quirk: `stop` often needs several attempts, so the
  integration sends it 5× — a stop can therefore take ~5 s to complete.

## Development

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e . pytest-homeassistant-custom-component aioresponses ruff mypy
pytest
ruff check . && mypy
```

Protocol documentation and response samples live in [docs/](docs/).

## Credits

API reverse engineering based on the vendor's "Accelev API v0.14" document and
a production Node-RED bridge that polled this API for ~2 years.
