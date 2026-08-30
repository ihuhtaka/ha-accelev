"""Diagnostics support for the Accelev EV Charger integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PIN
from homeassistant.core import HomeAssistant

from .coordinator import AccelevConfigEntry

TO_REDACT = {CONF_PIN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AccelevConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator_data": asdict(coordinator.data) if coordinator.data else None,
        "consecutive_failures": coordinator.consecutive_failures,
        "update_interval_seconds": coordinator.update_interval.total_seconds()
        if coordinator.update_interval
        else None,
    }
