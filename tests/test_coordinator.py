"""Tests for the Accelev coordinator and entities."""

from __future__ import annotations

from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import load_fixture, mock_info_payload, mock_values_payloads


async def _setup_entry(hass: HomeAssistant, mock_config_entry) -> None:
    mock_config_entry.add_to_hass(hass)
    with aioresponses() as mocked:
        mock_values_payloads(mocked)
        mock_info_payload(mocked)
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()


async def test_entities_created_and_populated(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """All entities are created and populated from the first refresh."""
    await _setup_entry(hass, mock_config_entry)

    entity_registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    keys = {e.unique_id.split("_", 1)[1] for e in entries}
    assert keys == {
        "voltage",
        "current",
        "power",
        "energy",
        "total_energy",
        "last_update",
        "info",
        "charging",
        "server_online",
        "charge",
        "grid_monitoring",
        "battery_care",
        "no_full_charging",
        "set_current",
        "sync_time",
    }

    assert hass.states.get("sensor.accelev_fa000000_voltage").state == "230.4"
    assert hass.states.get("sensor.accelev_fa000000_current").state == "0.0"
    # Native unit is kW; suggested unit W converts the displayed state.
    assert hass.states.get("sensor.accelev_fa000000_power").state == "7900.0"
    assert hass.states.get("sensor.accelev_fa000000_session_energy").state == "3.42"
    assert hass.states.get("sensor.accelev_fa000000_total_energy").state == "1234.5"
    assert hass.states.get("binary_sensor.accelev_fa000000_charging").state == "off"
    assert hass.states.get("binary_sensor.accelev_fa000000_server_online").state == "on"


async def test_charging_detection_from_current(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Current above threshold flips the charging binary sensor on."""
    await _setup_entry(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    with aioresponses() as mocked:
        mock_values_payloads(mocked, current=load_fixture("current_charging.txt"))
        mock_info_payload(mocked)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert coordinator.data.charging is True
    assert hass.states.get("binary_sensor.accelev_fa000000_charging").state == "on"


async def test_stale_values_report_not_charging(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Frozen charger-side snapshot -> not charging, current/power read 0."""
    await _setup_entry(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    # Active charging with fresh data (same last_time is fine briefly).
    with aioresponses() as mocked:
        mock_values_payloads(mocked, current=load_fixture("current_charging.txt"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert coordinator.data.charging is True
    assert coordinator.data.stale is False

    # Simulate > STALE_AFTER_SECONDS without last_time advancing, while the
    # server keeps serving the phantom 11.5 A reading.
    coordinator._last_fresh -= 400
    with aioresponses() as mocked:
        mock_values_payloads(mocked, current=load_fixture("current_charging.txt"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert coordinator.data.stale is True
    assert coordinator.data.charging is False
    assert coordinator.data.values.current == 0.0
    assert coordinator.data.values.power == 0.0
    state = hass.states.get("binary_sensor.accelev_fa000000_charging")
    assert state.state == "off"
    assert state.attributes["data_stale"] is True


async def test_transient_failure_keeps_data(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """A single failed cycle keeps previous data and availability."""
    await _setup_entry(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    with aioresponses():  # no routes registered -> every request fails
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert coordinator.last_update_success is True  # single failure tolerated
    voltage = hass.states.get("sensor.accelev_fa000000_voltage")
    assert voltage.state == "230.4"

    # Second consecutive failure -> entities go unavailable.
    with aioresponses():
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert hass.states.get("sensor.accelev_fa000000_voltage").state == "unavailable"
    # ... but the connectivity sensor stays available and reads "off".
    assert (
        hass.states.get("binary_sensor.accelev_fa000000_server_online").state == "off"
    )
