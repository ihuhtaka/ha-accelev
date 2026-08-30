"""Async client for the Accelev / EVTUN cloud API.

The API is plain HTTP GET with credentials as query parameters on every
request. Responses are plain text: bare floats for value queries, a
human-readable sentence for ``info``, and ``1``/``0`` for acknowledged
commands. See ``docs/protocol.md`` for the full reference.

This module intentionally has no Home Assistant imports so it can be
tested in isolation.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp

from .const import BASE_URL, REQUEST_TIMEOUT, STOP_SEND_ATTEMPTS, STOP_SEND_DELAY

_FLOAT_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_INFO_SERIAL_RE = re.compile(r"^([A-Za-z0-9]+)")
_INFO_TOTAL_ENERGY_RE = re.compile(r"Total energy is\s+([\d.,]+)\s*kWh", re.IGNORECASE)
_INFO_SOP_RE = re.compile(r"Overall SOP is\s+([\d.,]+)", re.IGNORECASE)
_INFO_FIRMWARE_RE = re.compile(r"Firmware ver(?:sion)?\s+is\s+([\d.,]+)", re.IGNORECASE)
# Bad-credentials response body is undocumented; match the plausible phrasing
# and refine from live captures (docs/protocol.md).
_AUTH_FAILURE_RE = re.compile(
    r"(wrong|invalid|incorrect|denied).{0,30}(pin|charger|serial|auth)",
    re.IGNORECASE,
)


class AccelevError(Exception):
    """Base exception for Accelev API errors."""


class AccelevConnectionError(AccelevError):
    """The API server could not be reached or returned an HTTP error."""


class AccelevAuthError(AccelevError):
    """The charger ID or PIN was rejected."""


class AccelevCommandRejectedError(AccelevError):
    """A command was sent with ack=1 and the charger answered ``0``."""


class AccelevParseError(AccelevError):
    """The response body could not be parsed."""


@dataclass(frozen=True)
class AccelevValues:
    """Polled live values from the charger."""

    voltage: float  # V
    current: float  # A, actual current to the car (not the setpoint)
    energy: float  # kWh, session energy (resets each charge)
    power: float  # kW
    last_time: str  # HH:MM:SS, charger-local time of the reading


@dataclass(frozen=True)
class AccelevInfo:
    """Parsed result of the ``info`` command."""

    raw: str
    serial: str | None
    total_energy_kwh: float | None
    sop: float | None
    firmware: str | None


def _parse_float(text: str, *, command: str) -> float:
    """Extract the first float from a response body (comma decimals tolerated)."""
    if match := _FLOAT_RE.search(text):
        return float(match.group(0).replace(",", "."))
        # Note: comma-separated thousands in `info` fields are not expected.
    raise AccelevParseError(f"No number found in response to {command!r}: {text!r}")


def _parse_optional_float(pattern: re.Pattern[str], text: str) -> float | None:
    if match := pattern.search(text):
        return float(match.group(1).replace(",", ""))
    return None


class AccelevApiClient:
    """Thin async wrapper around the Accelev cloud API."""

    def __init__(
        self,
        charger_id: str,
        pin: str,
        session: aiohttp.ClientSession,
        *,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        """Initialize the client.

        ``session`` must be owned by the caller (pass Home Assistant's shared
        aiohttp session).
        """
        self.charger_id = charger_id
        self._pin = pin
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _async_get(self, fragment: str) -> str:
        """Perform a GET with credentials plus a raw command fragment.

        The fragment is appended verbatim (e.g. ``"info"`` or
        ``"start=true&ack=1"``), mirroring the URLs the vendor documents.
        """
        url = (
            f"{BASE_URL}?charger={quote(self.charger_id)}"
            f"&pin={quote(self._pin)}&{fragment}"
        )
        try:
            async with self._session.get(url, timeout=self._timeout) as response:
                if response.status >= 400:
                    raise AccelevConnectionError(f"API returned HTTP {response.status}")
                body = (await response.text()).strip()
        except AccelevConnectionError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise AccelevConnectionError(f"API request failed: {err}") from err

        if _AUTH_FAILURE_RE.search(body):
            raise AccelevAuthError(f"API rejected credentials: {body!r}")
        return body

    @staticmethod
    def _check_ack(body: str, command: str) -> None:
        """Validate an ack=1 command response.

        Verified live: ``current=12&ack=1`` returns ``11`` (apparently one
        ack digit per processed command), while the vendor doc shows ``1``
        for success and ``0`` for rejection. Rule: success = non-empty body
        consisting only of ``1`` digits; anything else (empty, contains 0,
        or unexpected text) is a rejection.
        """
        if not body or any(digit != "1" for digit in body):
            raise AccelevCommandRejectedError(
                f"Command {command!r} was rejected by the charger (response: {body!r})"
            )

    async def _async_query_float(self, command: str) -> float:
        return _parse_float(await self._async_get(f"{command}=ask"), command=command)

    async def async_get_values(self) -> AccelevValues:
        """Fetch all live values in one concurrent batch."""
        voltage, current, energy, power, last_time = await asyncio.gather(
            self._async_query_float("whatisvoltage"),
            self._async_query_float("whatiscurrent"),
            self._async_query_float("whatisenergy"),
            self._async_query_float("whatispower"),
            self._async_get("whatislasttime=ask"),
        )
        return AccelevValues(
            voltage=voltage,
            current=current,
            energy=energy,
            power=power,
            last_time=last_time,
        )

    async def async_get_info(self) -> AccelevInfo:
        """Fetch and parse charger info (lifetime energy, SOP, firmware)."""
        body = await self._async_get("info")
        if not body:
            # Verified 2026-08-26: bad PIN / unknown charger ID -> HTTP 200
            # with an empty body. (An offline charger may look the same; the
            # config flow treats this as invalid_auth, the poller degrades
            # gracefully instead of triggering reauth storms.)
            raise AccelevAuthError(
                "Empty response to 'info' — charger ID or PIN rejected"
            )
        serial_match = _INFO_SERIAL_RE.search(body)
        firmware_match = _INFO_FIRMWARE_RE.search(body)
        return AccelevInfo(
            raw=body,
            serial=serial_match.group(1) if serial_match else None,
            total_energy_kwh=_parse_optional_float(_INFO_TOTAL_ENERGY_RE, body),
            sop=_parse_optional_float(_INFO_SOP_RE, body),
            firmware=firmware_match.group(1) if firmware_match else None,
        )

    async def async_validate_credentials(self) -> AccelevInfo:
        """Validate charger ID + PIN. Returns parsed info on success."""
        return await self.async_get_info()

    async def async_set_current(self, amps: float) -> None:
        """Set the charge current in amps."""
        body = await self._async_get(f"current={amps:g}&ack=1")
        self._check_ack(body, f"current={amps:g}")

    async def async_start_charging(self) -> None:
        """Start charging."""
        body = await self._async_get("start=true&ack=1")
        self._check_ack(body, "start=true")

    async def async_stop_charging(self) -> None:
        """Stop charging.

        Firmware quirk: a single stop is frequently ignored, so send it
        STOP_SEND_ATTEMPTS times ~1 s apart (recipe proven by years of
        production use). Every attempt's ack is validated.
        """
        for attempt in range(STOP_SEND_ATTEMPTS):
            body = await self._async_get("stop=true&ack=1")
            self._check_ack(body, "stop=true")
            if attempt < STOP_SEND_ATTEMPTS - 1:
                await asyncio.sleep(STOP_SEND_DELAY)

    async def async_set_grid_monitoring(self, enabled: bool) -> None:
        """Enable or disable grid monitoring."""
        value = "on" if enabled else "off"
        body = await self._async_get(f"gridm={value}&ack=1")
        self._check_ack(body, f"gridm={value}")

    async def async_set_battery_care(self, enabled: bool) -> None:
        """Enable or disable BatteryCare."""
        value = "on" if enabled else "off"
        body = await self._async_get(f"batcare={value}&ack=1")
        self._check_ack(body, f"batcare={value}")

    async def async_set_no_full_charging(self, enabled: bool) -> None:
        """Enable or disable the no-full-charging mode."""
        value = "on" if enabled else "off"
        body = await self._async_get(f"nofull={value}&ack=1")
        self._check_ack(body, f"nofull={value}")

    async def async_set_time(self, hhmm: str) -> None:
        """Set the charger clock. ``hhmm`` must be 4 zero-padded chars."""
        body = await self._async_get(f"settime={hhmm}&ack=1")
        self._check_ack(body, f"settime={hhmm}")
