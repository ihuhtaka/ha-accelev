"""Tests for the Accelev charge switch state override."""

from __future__ import annotations

from aioresponses import aioresponses
from homeassistant.core import HomeAssistant

from .conftest import (
    AUTH_QS,
    BASE_URL,
    load_fixture,
    mock_info_payload,
    mock_values_payloads,
)

CHARGE_SWITCH = "switch.accelev_fa000000_charge"


async def _setup_charging(hass: HomeAssistant, mock_config_entry) -> None:
    """Set up the entry while the API reports active charging."""
    mock_config_entry.add_to_hass(hass)
    with aioresponses() as mocked:
        mock_values_payloads(mocked, current=load_fixture("current_charging.txt"))
        mock_info_payload(mocked)
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()


async def test_charge_switch_stays_off_after_stop(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Stop shows 'off' immediately despite phantom current in the API.

    Regression test: after a stop, the server keeps serving the last current
    reading for minutes (staleness window), which used to bounce the polled
    charge switch back on.
    """
    await _setup_charging(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert coordinator.data.charging is True

    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}?{AUTH_QS}&stop=true&ack=1", body="11", repeat=True)
        # Phantom: server keeps reporting 11.5 A even though stop was sent.
        mock_values_payloads(mocked, current=load_fixture("current_charging.txt"))
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": CHARGE_SWITCH}, blocking=True
        )
        await hass.async_block_till_done()

    assert coordinator.data.charging is True  # polled truth still phantom
    assert hass.states.get(CHARGE_SWITCH).state == "off"


async def test_charge_switch_stays_on_after_start(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Start shows 'on' immediately even while values are still stale-zero."""
    mock_config_entry.add_to_hass(hass)
    with aioresponses() as mocked:
        mock_values_payloads(mocked)  # idle zeros
        mock_info_payload(mocked)
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    coordinator = mock_config_entry.runtime_data
    assert coordinator.data.charging is False

    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}?{AUTH_QS}&start=true&ack=1", body="11")
        mock_values_payloads(mocked)  # still zeros right after start
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": CHARGE_SWITCH}, blocking=True
        )
        await hass.async_block_till_done()

    assert coordinator.data.charging is False  # polled truth not there yet
    assert hass.states.get(CHARGE_SWITCH).state == "on"
