"""Tests for the Accelev API client."""

from __future__ import annotations

import pytest
from aioresponses import CallbackResult, aioresponses

from custom_components.accelev.api import (
    AccelevApiClient,
    AccelevAuthError,
    AccelevCommandRejectedError,
    AccelevConnectionError,
    AccelevParseError,
    _parse_float,
)
from custom_components.accelev.const import STOP_SEND_ATTEMPTS

from .conftest import (
    AUTH_QS,
    BASE_URL,
    MOCK_CHARGER_ID,
    MOCK_PIN,
    load_fixture,
    mock_info_payload,
    mock_values_payloads,
)


@pytest.fixture(name="client")
async def client_fixture(hass) -> AccelevApiClient:
    """Return a client bound to the test aiohttp session."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    return AccelevApiClient(MOCK_CHARGER_ID, MOCK_PIN, async_get_clientsession(hass))


def test_parse_float_bare_number() -> None:
    """Bare-number responses parse."""
    assert _parse_float("230.4", command="x") == 230.4
    assert _parse_float("0", command="x") == 0.0


def test_parse_float_sentence_and_comma_decimal() -> None:
    """Sentence-style and comma-decimal responses parse tolerantly."""
    assert _parse_float("Voltage is 231.7 V", command="x") == 231.7
    assert _parse_float("6,5", command="x") == 6.5


def test_parse_float_no_number() -> None:
    """Bodies without numbers raise AccelevParseError."""
    with pytest.raises(AccelevParseError):
        _parse_float("no data", command="whatisvoltage")


async def test_get_values(hass, client: AccelevApiClient) -> None:
    """All five values are fetched and parsed."""
    with aioresponses() as mocked:
        mock_values_payloads(mocked, current=load_fixture("current_charging.txt"))
        values = await client.async_get_values()

    assert values.voltage == 230.4
    assert values.current == 11.5
    assert values.energy == 3.42
    assert values.power == 7.9
    assert values.last_time == "14:32:05"


async def test_get_info_parses_fields(hass, client: AccelevApiClient) -> None:
    """The info sentence is parsed into structured fields."""
    with aioresponses() as mocked:
        mock_info_payload(mocked)
        info = await client.async_get_info()

    assert info.serial == "FA000000"
    assert info.total_energy_kwh == 1234.5
    assert info.sop == 3.7
    assert info.firmware == "2.73"
    assert "Total energy" in info.raw


async def test_empty_info_body_means_auth_error(hass, client: AccelevApiClient) -> None:
    """Empty info body = rejected credentials (verified live 2026-08-26)."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}?{AUTH_QS}&info", body="")
        with pytest.raises(AccelevAuthError):
            await client.async_get_info()


async def test_commands_send_ack_and_validate(hass, client: AccelevApiClient) -> None:
    """Write commands hit the documented URLs and accept ack=1."""
    endpoints = {
        "start=true&ack=1": client.async_start_charging,
        "stop=true&ack=1": client.async_stop_charging,
        "current=16&ack=1": lambda: client.async_set_current(16),
        "current=6.5&ack=1": lambda: client.async_set_current(6.5),
        "gridm=on&ack=1": lambda: client.async_set_grid_monitoring(True),
        "gridm=off&ack=1": lambda: client.async_set_grid_monitoring(False),
        "batcare=on&ack=1": lambda: client.async_set_battery_care(True),
        "nofull=on&ack=1": lambda: client.async_set_no_full_charging(True),
        "settime=0642&ack=1": lambda: client.async_set_time("0642"),
    }
    with aioresponses() as mocked:
        for fragment in endpoints:
            # repeat=True: stop is intentionally sent multiple times
            mocked.get(f"{BASE_URL}?{AUTH_QS}&{fragment}", body="1", repeat=True)
        for call in endpoints.values():
            await call()  # raises if ack validation fails


async def test_command_rejected(hass, client: AccelevApiClient) -> None:
    """An ack=0 response raises AccelevCommandRejectedError."""
    with aioresponses() as mocked:
        # stop is sent STOP_SEND_ATTEMPTS times; fail every attempt
        mocked.get(f"{BASE_URL}?{AUTH_QS}&stop=true&ack=1", body="0", repeat=True)
        with pytest.raises(AccelevCommandRejectedError):
            await client.async_stop_charging()


async def test_multi_digit_ack_accepted(hass, client: AccelevApiClient) -> None:
    """Real chargers answer e.g. '11' to current=12&ack=1 — must be accepted."""
    with aioresponses() as mocked:
        mocked.get(
            f"{BASE_URL}?{AUTH_QS}&current=12&ack=1",
            body=load_fixture("ack_multi.txt"),
        )
        await client.async_set_current(12)  # must not raise


async def test_stop_sent_multiple_times(hass, client: AccelevApiClient) -> None:
    """Stop is sent STOP_SEND_ATTEMPTS times (flaky firmware workaround)."""
    calls = 0

    def callback(url, **kwargs):
        nonlocal calls
        calls += 1
        return CallbackResult(status=200, body="11")

    with aioresponses() as mocked:
        mocked.get(
            f"{BASE_URL}?{AUTH_QS}&stop=true&ack=1",
            callback=callback,
            repeat=True,
        )
        await client.async_stop_charging()
    assert calls == STOP_SEND_ATTEMPTS


async def test_bad_pin_raises_auth_error(hass, client: AccelevApiClient) -> None:
    """A wrong-pin response body raises AccelevAuthError."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}?{AUTH_QS}&info", body=load_fixture("auth_error.txt"))
        with pytest.raises(AccelevAuthError):
            await client.async_get_info()


async def test_timeout_raises_connection_error(hass, client: AccelevApiClient) -> None:
    """Network timeouts raise AccelevConnectionError."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}?{AUTH_QS}&info", exception=TimeoutError())
        with pytest.raises(AccelevConnectionError):
            await client.async_get_info()


async def test_http_error_raises_connection_error(
    hass, client: AccelevApiClient
) -> None:
    """HTTP >= 400 raises AccelevConnectionError."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}?{AUTH_QS}&info", status=500)
        with pytest.raises(AccelevConnectionError):
            await client.async_get_info()
