"""Constants for the Accelev EV Charger integration."""

from typing import Final

DOMAIN: Final = "accelev"

CONF_CHARGER_ID: Final = "charger_id"

BASE_URL: Final = "http://server.evtun.com:8091/api.php"
REQUEST_TIMEOUT: Final = 15.0  # seconds per HTTP call

# Polling. The old production system polled values every 60 s and `info`
# every 300 s for years without issues, so stay within that envelope.
DEFAULT_SCAN_INTERVAL: Final = 60  # seconds
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 600
INFO_EVERY_N_CYCLES: Final = 5  # fetch `info` on every Nth cycle

# Set-current limits. Vendor doc allows 6-32 A; capped at 24 A per the
# owner's hardware installation.
MIN_CURRENT: Final = 6.0
MAX_CURRENT: Final = 24.0
CURRENT_STEP: Final = 0.5

# Charging detection hysteresis (actual current to car, amps), plus an
# energy-delta fallback for chargers that report 0 A while charging.
CHARGING_ON_THRESHOLD: Final = 0.3
CHARGING_OFF_THRESHOLD: Final = 0.1
ENERGY_RISING_EPSILON: Final = 0.0001  # kWh

# Stale-data handling. While charging, the charger uploads fresh values about
# once a minute. After a stop, uploads CEASE and the server keeps serving the
# last reading forever (verified live 2026-08-26: current kept reading 5.9 A
# for 2+ hours with energy frozen). If `whatislasttime` has not advanced for
# this long, the snapshot is stale: report current/power as 0 and not
# charging. 180 s = 3 missed uploads (~60 s cadence) with margin.
STALE_AFTER_SECONDS: Final = 180.0

# Firmware quirk (owner-verified over years): a single `stop` is often
# ignored; send it several times ~1 s apart.
STOP_SEND_ATTEMPTS: Final = 5
STOP_SEND_DELAY: Final = 1.0  # seconds

# After a start/stop command the API keeps serving stale readings for a while
# (up to STALE_AFTER_SECONDS + one poll cycle after a stop). The charge switch
# would otherwise bounce back to the polled (phantom) state, so it overrides
# the polled state briefly after a successful command.
CHARGE_SWITCH_OVERRIDE_ON: Final = 150.0  # values unfreeze within ~60-90 s of start
CHARGE_SWITCH_OVERRIDE_OFF: Final = 300.0  # staleness trips within ~240 s of stop

# Number of consecutive failed poll cycles before entities go unavailable.
CONSECUTIVE_FAILURES_BEFORE_UNAVAILABLE: Final = 2

MANUFACTURER: Final = "Accelev (EVTUN)"
MODEL: Final = "Accelev EV Charger"
