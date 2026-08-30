"""Tests for the Accelev config flow."""

from __future__ import annotations

from aioresponses import aioresponses
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.accelev.const import CONF_CHARGER_ID, DOMAIN

from .conftest import (
    AUTH_QS,
    BASE_URL,
    MOCK_CHARGER_ID,
    MOCK_PIN,
    load_fixture,
    mock_info_payload,
)


async def test_full_flow(hass: HomeAssistant) -> None:
    """Happy path: form shown, then entry created on valid credentials."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert not result["errors"]

    with aioresponses() as mocked:
        mock_info_payload(mocked)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CHARGER_ID: MOCK_CHARGER_ID, CONF_PIN: MOCK_PIN},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Accelev {MOCK_CHARGER_ID}"
    assert result["data"] == {
        CONF_CHARGER_ID: MOCK_CHARGER_ID,
        CONF_PIN: MOCK_PIN,
    }


async def test_unique_id_from_serial_and_duplicate_abort(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """The entry unique ID is the serial from `info`; duplicates abort."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with aioresponses() as mocked:
        mock_info_payload(mocked)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CHARGER_ID: MOCK_CHARGER_ID, CONF_PIN: MOCK_PIN},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_cannot_connect(hass: HomeAssistant) -> None:
    """Timeout during validation shows cannot_connect."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}?{AUTH_QS}&info", exception=TimeoutError())
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CHARGER_ID: MOCK_CHARGER_ID, CONF_PIN: MOCK_PIN},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_invalid_auth(hass: HomeAssistant) -> None:
    """Rejected credentials show invalid_auth (textual error body)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}?{AUTH_QS}&info", body=load_fixture("auth_error.txt"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CHARGER_ID: MOCK_CHARGER_ID, CONF_PIN: MOCK_PIN},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_invalid_auth_empty_body(hass: HomeAssistant) -> None:
    """Empty info body (the real bad-PIN response, verified live) -> invalid_auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}?{AUTH_QS}&info", body="")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CHARGER_ID: MOCK_CHARGER_ID, CONF_PIN: MOCK_PIN},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_options_flow(hass: HomeAssistant, mock_config_entry) -> None:
    """Options flow updates the scan interval."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 120}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {"scan_interval": 120}
