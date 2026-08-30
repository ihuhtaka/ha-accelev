"""DataUpdateCoordinator for the Accelev EV Charger integration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AccelevApiClient,
    AccelevAuthError,
    AccelevError,
    AccelevInfo,
    AccelevValues,
)
from .const import (
    CHARGING_OFF_THRESHOLD,
    CHARGING_ON_THRESHOLD,
    CONSECUTIVE_FAILURES_BEFORE_UNAVAILABLE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENERGY_RISING_EPSILON,
    INFO_EVERY_N_CYCLES,
    STALE_AFTER_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

type AccelevConfigEntry = ConfigEntry[AccelevDataUpdateCoordinator]


@dataclass
class AccelevData:
    """Everything the coordinator knows after a poll cycle."""

    values: AccelevValues | None = None
    info: AccelevInfo | None = None
    charging: bool = False
    stale: bool = False


class AccelevDataUpdateCoordinator(DataUpdateCoordinator[AccelevData]):
    """Polls the Accelev cloud API on a fixed interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: AccelevConfigEntry,
        client: AccelevApiClient,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.entry = config_entry
        self._failures = 0
        self._cycle = 0
        self._last_fresh = time.monotonic()
        interval = int(
            config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    @property
    def consecutive_failures(self) -> int:
        """Return the number of consecutive failed poll cycles (diagnostics)."""
        return self._failures

    async def _async_update_data(self) -> AccelevData:
        previous = self.data
        try:
            values = await self.client.async_get_values()
        except AccelevAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
            ) from err
        except AccelevError as err:
            self._failures += 1
            if (
                previous is None
                or self._failures >= CONSECUTIVE_FAILURES_BEFORE_UNAVAILABLE
            ):
                raise UpdateFailed(
                    f"Error communicating with Accelev API: {err}"
                ) from err
            _LOGGER.debug(
                "Transient Accelev API failure %d/%d, keeping previous data: %s",
                self._failures,
                CONSECUTIVE_FAILURES_BEFORE_UNAVAILABLE,
                err,
            )
            return previous
        self._failures = 0

        # Staleness detection: after a stop (or if the charger goes quiet) the
        # server keeps serving the last snapshot forever, including a phantom
        # current reading. `last_time` advancing is the only freshness signal.
        now = time.monotonic()
        if (
            previous is None
            or previous.values is None
            or (values.last_time != previous.values.last_time)
        ):
            self._last_fresh = now
        stale = (now - self._last_fresh) > STALE_AFTER_SECONDS
        if stale:
            _LOGGER.debug(
                "Accelev values are stale (last report %s) — treating current "
                "and power as 0",
                values.last_time,
            )
            values = replace(values, current=0.0, power=0.0)

        # `info` is fetched on a slower cadence; a failure here must not
        # kill the whole cycle.
        info = previous.info if previous else None
        self._cycle = (self._cycle + 1) % INFO_EVERY_N_CYCLES
        if info is None or self._cycle == 0:
            try:
                info = await self.client.async_get_info()
            except AccelevError as err:
                _LOGGER.debug("Could not fetch Accelev info: %s", err)

        return AccelevData(
            values=values,
            info=info,
            charging=False if stale else self._compute_charging(values, previous),
            stale=stale,
        )

    @staticmethod
    def _compute_charging(values: AccelevValues, previous: AccelevData | None) -> bool:
        """Derive the charging state with hysteresis + energy-delta fallback.

        Primary signal is actual current to the car. Some firmware reads 0 A
        while charging, so a rising session-energy counter also counts as
        charging (replacing the old 15-minute-delay heuristic).
        """
        energy_rising = (
            previous is not None
            and previous.values is not None
            and values.energy > previous.values.energy + ENERGY_RISING_EPSILON
        )
        was_charging = previous.charging if previous else False
        if was_charging:
            return values.current > CHARGING_OFF_THRESHOLD or energy_rising
        return values.current > CHARGING_ON_THRESHOLD or energy_rising
