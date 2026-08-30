"""Test fixtures and helpers for the Accelev integration."""

from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant.const import CONF_PIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.accelev.const import CONF_CHARGER_ID, DOMAIN

FIXTURES_DIR = Path(__file__).parent / "fixtures"

MOCK_CHARGER_ID = "FA000000"
MOCK_PIN = "000000"
MOCK_SERIAL = "FA000000"

BASE_URL = "http://server.evtun.com:8091/api.php"
AUTH_QS = f"charger={MOCK_CHARGER_ID}&pin={MOCK_PIN}"


def load_fixture(name: str) -> str:
    """Load a raw API response fixture."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8").strip()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations for all tests."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Accelev {MOCK_CHARGER_ID}",
        unique_id=MOCK_SERIAL,
        data={CONF_CHARGER_ID: MOCK_CHARGER_ID, CONF_PIN: MOCK_PIN},
    )


def mock_values_payloads(
    mocked,
    *,
    current: str | None = None,
    energy: str | None = None,
) -> None:
    """Register the five `whatis*` endpoints on an aioresponses mock."""
    mocked.get(
        f"{BASE_URL}?{AUTH_QS}&whatisvoltage=ask",
        body=load_fixture("voltage.txt"),
    )
    mocked.get(
        f"{BASE_URL}?{AUTH_QS}&whatiscurrent=ask",
        body=current if current is not None else load_fixture("current_idle.txt"),
    )
    mocked.get(
        f"{BASE_URL}?{AUTH_QS}&whatisenergy=ask",
        body=energy if energy is not None else load_fixture("energy.txt"),
    )
    mocked.get(
        f"{BASE_URL}?{AUTH_QS}&whatispower=ask",
        body=load_fixture("power.txt"),
    )
    mocked.get(
        f"{BASE_URL}?{AUTH_QS}&whatislasttime=ask",
        body=load_fixture("lasttime.txt"),
    )


def mock_info_payload(mocked) -> None:
    """Register the `info` endpoint on an aioresponses mock."""
    mocked.get(f"{BASE_URL}?{AUTH_QS}&info", body=load_fixture("info.txt"))
