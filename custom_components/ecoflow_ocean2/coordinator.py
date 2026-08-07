"""Coordinator: haelt die MQTT-Verbindung und verteilt Snapshots.

Push-Modell: kein ``update_interval``, stattdessen ``async_set_updated_data()``
bei jeder verwertbaren Nachricht. Das Geraet sendet ca. alle 2 Sekunden -
deutlich zu oft fuer die State Machine, deshalb die Drossel.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import (
    EcoflowAuthError,
    EcoflowConnectionError,
    EcoflowMqttClient,
    async_fetch_mqtt_credentials,
    async_login,
)
from .const import (
    QUOTA_TRIGGER_INTERVAL,
    RECONNECT_BACKOFF_MAX,
    RECONNECT_BACKOFF_START,
)
from .capture import FrameCapture
from .protobuf import decode_mqtt_payload
from .snapshot import Snapshot, merge_snapshot

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

#: Mindestabstand zwischen State-Updates. Ungedrosselt entstuenden ~43.000
#: Zustandsaenderungen je Sensor und Tag - das belastet Recorder und SD-Karte.
MIN_UPDATE_INTERVAL = 10.0

#: Ohne Nachricht in diesem Zeitraum gelten die Daten als veraltet.
STALE_AFTER = 120.0


class EcoflowCoordinator(DataUpdateCoordinator[Snapshot]):
    """Verteilt die per MQTT empfangenen Snapshots an die Entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        email: str,
        password: str,
        device_sn: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"EcoFlow PowerOcean {device_sn}",
            config_entry=entry,
            # Kein update_interval: die Daten kommen gepusht.
        )
        self._email = email
        self._password = password
        self._device_sn = device_sn
        self._client: EcoflowMqttClient | None = None
        self._snapshot: Snapshot | None = None
        self._last_push = 0.0
        self._last_message = 0.0
        #: Mitschnitt fuer die Diagnose - siehe capture.py.
        self._capture = FrameCapture(device_sn)
        self._connected = False
        self._first_data = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()

    @property
    def device_sn(self) -> str:
        return self._device_sn

    @property
    def connected(self) -> bool:
        """True, wenn MQTT verbunden ist und zuletzt Daten kamen."""
        if not self._connected:
            return False
        return (time.monotonic() - self._last_message) < STALE_AFTER

    # ── Lebenszyklus ─────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Verbindet und wartet auf die ersten Daten."""
        await self._async_connect()
        self._spawn(self._async_keepalive_loop(), "keepalive")
        self._spawn(self._async_watchdog_loop(), "watchdog")

        try:
            async with asyncio.timeout(45):
                await self._first_data.wait()
        except TimeoutError:
            # Kein harter Fehler: Das Geraet meldet sich manchmal erst nach dem
            # naechsten Weckruf. Die Entities sind dann kurz nicht verfuegbar.
            _LOGGER.warning("No data within 45 s - waiting for the device to report")

    async def async_stop(self) -> None:
        """Alles abbauen - MQTT-Verbindung und Hintergrund-Tasks."""
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        if self._client is not None:
            await self._client.async_disconnect()
            self._client = None
        self._connected = False

    def _spawn(self, coro, name: str) -> None:
        task = self.hass.async_create_background_task(
            coro, name=f"ecoflow_ocean2_{name}"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ── Verbindung ───────────────────────────────────────────────────────────

    async def _async_connect(self) -> None:
        """Login, MQTT-Zugangsdaten holen und verbinden."""
        session = async_get_clientsession(self.hass)
        try:
            token, user_id = await async_login(session, self._email, self._password)
            credentials = await async_fetch_mqtt_credentials(session, token, user_id)
        except EcoflowAuthError as err:
            # Loest den Reauth-Dialog in Home Assistant aus
            raise ConfigEntryAuthFailed(str(err)) from err

        self._client = EcoflowMqttClient(
            loop=self.hass.loop,
            credentials=credentials,
            device_sn=self._device_sn,
            on_payload=self._handle_payload,
            on_connection_change=self._handle_connection_change,
        )
        await self._client.async_connect()

    async def _async_keepalive_loop(self) -> None:
        """Regelmaessiger Weckruf - sonst versiegt der Datenstrom."""
        while True:
            await asyncio.sleep(QUOTA_TRIGGER_INTERVAL)
            if self._client is not None:
                self._client.request_latest_quotas()

    async def _async_watchdog_loop(self) -> None:
        """Holt bei anhaltender Stille neue Zugangsdaten und verbindet neu.

        Ein blosser MQTT-Reconnect hilft nicht, wenn Token oder Zertifikat
        abgelaufen sind - dann muss der komplette Login wiederholt werden.
        """
        backoff = RECONNECT_BACKOFF_START
        while True:
            await asyncio.sleep(30)
            if self.connected:
                backoff = RECONNECT_BACKOFF_START
                continue

            _LOGGER.warning("No data for %.0f s - reconnecting", STALE_AFTER)
            try:
                if self._client is not None:
                    await self._client.async_disconnect()
                    self._client = None
                await self._async_connect()
            except ConfigEntryAuthFailed:
                raise
            except (EcoflowConnectionError, aiohttp.ClientError, OSError) as err:
                _LOGGER.warning("Reconnect failed: %s", err)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX)

    # ── Datenfluss ───────────────────────────────────────────────────────────

    @callback
    def _handle_connection_change(self, connected: bool) -> None:
        if connected == self._connected:
            return
        self._connected = connected
        _LOGGER.info("MQTT %s", "connected" if connected else "disconnected")
        if not connected and self._snapshot is not None:
            # Entities sofort als nicht verfuegbar markieren, statt alte Werte
            # als aktuell auszugeben.
            self.async_update_listeners()

    @property
    def capture(self) -> FrameCapture:
        """Mitschnitt der Rohnachrichten, nur fuer die Diagnose."""
        return self._capture

    @callback
    def _handle_payload(self, payload: bytes) -> None:
        # Vor dem Dekodieren: Was der Parser nicht versteht, kehrt unten
        # stillschweigend zurueck - und genau das ist bei einem unbekannten
        # Geraet das Interessante.
        self._capture.add(payload)

        try:
            message = decode_mqtt_payload(payload)
        except Exception:  # noqa: BLE001 - ein defektes Paket darf nichts reissen
            _LOGGER.debug("Could not decode payload (%d bytes)", len(payload))
            return

        if not message.has_payload():
            return

        now = time.monotonic()
        self._last_message = now
        self._snapshot = merge_snapshot(
            self._device_sn, self._snapshot, message, now=time.time()
        )

        if not self._first_data.is_set():
            self._first_data.set()
        elif now - self._last_push < MIN_UPDATE_INTERVAL:
            return

        self._last_push = now
        self.async_set_updated_data(self._snapshot)
