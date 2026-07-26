"""Konstanten der EcoFlow-PowerOcean-Integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ecoflow_ocean2"

CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_SN: Final = "device_sn"

MANUFACTURER: Final = "EcoFlow"
MODEL: Final = "PowerOcean"

# EcoFlow-App-API (die offizielle Developer-API liefert fuer PowerOcean keine Livedaten)
LOGIN_URL: Final = "https://api.ecoflow.com/auth/login"
CERT_URL: Final = "https://api.ecoflow.com/iot-auth/app/certification"

# Ohne diesen regelmaessigen Weckruf sendet das Geraet keine Telemetrie,
# solange keine EcoFlow-App geoeffnet ist.
QUOTA_TRIGGER_INTERVAL: Final = 60

# Reconnect: nach so vielen Fehlversuchen werden Token und MQTT-Zertifikat
# komplett neu geholt, statt endlos mit abgelaufenen Zugangsdaten zu reconnecten.
RECONNECT_BACKOFF_START: Final = 5
RECONNECT_BACKOFF_MAX: Final = 300
