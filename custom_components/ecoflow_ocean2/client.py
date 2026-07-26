"""Anbindung an EcoFlows App-Cloud (Login + MQTT).

Warum nicht die offizielle Developer-API? Fuer PowerOcean liefert sie keine
Livedaten - jede Quota-Abfrage endet mit Fehler 1006 ("current device is not
allowed to get device info"), und das offizielle MQTT-Topic sendet nichts.
Der einzige funktionierende Weg ist der Broker, den auch die EcoFlow-App nutzt.

Ablauf:
    1. POST /auth/login                    -> Token + userId
    2. GET  /iot-auth/app/certification    -> MQTT-Zugangsdaten
    3. Subscribe /app/device/property/{SN} -> Protobuf-Telemetrie
    4. Publish  .../thing/property/get     -> "latestQuotas" als Weckruf

Schritt 4 ist keine Optimierung, sondern Voraussetzung: Ohne diesen Weckruf
sendet das Geraet nichts, solange keine EcoFlow-App geoeffnet ist.

paho-mqtt laeuft in einem eigenen Thread. Alle Callbacks reichen ihre Daten
deshalb ueber ``loop.call_soon_threadsafe`` in den Event-Loop.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import aiohttp
import paho.mqtt.client as mqtt

from .const import CERT_URL, LOGIN_URL

_LOGGER = logging.getLogger(__name__)


class EcoflowAuthError(Exception):
    """Zugangsdaten wurden abgelehnt."""


class EcoflowConnectionError(Exception):
    """EcoFlow-Cloud nicht erreichbar."""


@dataclass(frozen=True)
class MqttCredentials:
    """Kurzlebige MQTT-Zugangsdaten. Bewusst nie persistiert."""

    url: str
    port: int
    protocol: str
    username: str
    password: str
    user_id: str

    @property
    def uses_tls(self) -> bool:
        return self.protocol.lower() in ("mqtts", "ssl", "tls")


async def async_login(
    session: aiohttp.ClientSession, email: str, password: str
) -> tuple[str, str]:
    """Meldet am EcoFlow-Konto an; gibt (Token, userId) zurueck."""
    import base64

    try:
        async with session.post(
            LOGIN_URL,
            headers={"Content-Type": "application/json", "lang": "en_US"},
            json={
                "email": email,
                "password": base64.b64encode(password.encode()).decode(),
                "scene": "IOT_APP",
                "userType": "ECOFLOW",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
        raise EcoflowConnectionError(f"Cannot reach EcoFlow: {err}") from err

    if payload.get("code") != "0" or not payload.get("data"):
        # EcoFlow meldet falsche Zugangsdaten ueber den Code, nicht per HTTP-Status
        raise EcoflowAuthError(payload.get("message", "Login rejected"))

    data = payload["data"]
    return data["token"], str(data["user"]["userId"])


async def async_fetch_mqtt_credentials(
    session: aiohttp.ClientSession, token: str, user_id: str
) -> MqttCredentials:
    """Holt die MQTT-Zugangsdaten fuer den App-Broker."""
    try:
        async with session.get(
            CERT_URL,
            params={"userId": user_id},
            headers={"authorization": f"Bearer {token}", "content-type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
        raise EcoflowConnectionError(f"Cannot fetch MQTT credentials: {err}") from err

    if payload.get("code") != "0" or not payload.get("data"):
        raise EcoflowAuthError(payload.get("message", "Certification rejected"))

    data = payload["data"]
    return MqttCredentials(
        url=data["url"],
        port=int(data["port"]),
        protocol=data["protocol"],
        username=data["certificateAccount"],
        password=data["certificatePassword"],
        user_id=user_id,
    )


async def async_validate_credentials(
    session: aiohttp.ClientSession, email: str, password: str
) -> str:
    """Prueft Zugangsdaten im Config Flow; gibt die userId zurueck."""
    token, user_id = await async_login(session, email, password)
    await async_fetch_mqtt_credentials(session, token, user_id)
    return user_id


class EcoflowMqttClient:
    """Haelt die MQTT-Verbindung und reicht rohe Payloads weiter.

    Bewusst ohne Protobuf-/Snapshot-Wissen - das macht der Coordinator.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        credentials: MqttCredentials,
        device_sn: str,
        on_payload: Callable[[bytes], None],
        on_connection_change: Callable[[bool], None],
    ) -> None:
        self._loop = loop
        self._credentials = credentials
        self._device_sn = device_sn
        self._on_payload = on_payload
        self._on_connection_change = on_connection_change
        self._client: mqtt.Client | None = None

    @property
    def _property_topic(self) -> str:
        return f"/app/device/property/{self._device_sn}"

    @property
    def _get_topic(self) -> str:
        return f"/app/{self._credentials.user_id}/{self._device_sn}/thing/property/get"

    async def async_connect(self) -> None:
        """Baut die MQTT-Verbindung auf (blockierende Teile im Executor)."""
        creds = self._credentials
        # Der ANDROID_-Praefix ist noetig: Der Broker weist andere Client-IDs ab.
        client_id = f"ANDROID_{uuid.uuid4().hex.upper()}_{creds.user_id}"

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
        client.username_pw_set(creds.username, creds.password)
        if creds.uses_tls:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.on_connect = self._handle_connect
        client.on_message = self._handle_message
        client.on_disconnect = self._handle_disconnect

        # connect() blockiert (DNS + TLS-Handshake) - nie im Event-Loop.
        await self._loop.run_in_executor(
            None, client.connect, creds.url, creds.port, 30
        )
        client.loop_start()
        self._client = client

    async def async_disconnect(self) -> None:
        """Verbindung sauber schliessen."""
        client, self._client = self._client, None
        if client is None:
            return
        client.disconnect()
        await self._loop.run_in_executor(None, client.loop_stop)

    def request_latest_quotas(self) -> None:
        """Weckruf ans Geraet - ohne diesen versiegt der Datenstrom."""
        client = self._client
        if client is None or not client.is_connected():
            return
        import json
        import random

        client.publish(
            self._get_topic,
            json.dumps(
                {
                    "from": "Android",
                    "id": str(random.randint(0, 999_999_999)),
                    "moduleType": 0,
                    "operateType": "latestQuotas",
                    "params": {},
                    "version": "1.0",
                }
            ),
        )

    # ── paho-Callbacks (laufen im MQTT-Thread!) ──────────────────────────────

    def _handle_connect(
        self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None
    ) -> None:
        if reason_code != 0:
            _LOGGER.warning("MQTT connection refused: %s", reason_code)
            return
        client.subscribe(self._property_topic)
        self._loop.call_soon_threadsafe(self._on_connection_change, True)
        self._loop.call_soon_threadsafe(self.request_latest_quotas)

    def _handle_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        payload = message.payload
        self._loop.call_soon_threadsafe(self._on_payload, payload)

    def _handle_disconnect(
        self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any = None, properties: Any = None
    ) -> None:
        self._loop.call_soon_threadsafe(self._on_connection_change, False)
