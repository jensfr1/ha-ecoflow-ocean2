"""Diagnosedaten - hilfreich fuer Fehlersuche, ohne Zugangsdaten preiszugeben."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import EcoflowConfigEntry
from .const import CONF_DEVICE_SN

#: Zugangsdaten und Seriennummer werden entfernt - Diagnosedaten landen
#: erfahrungsgemaess in oeffentlichen Issues.
REDACT = {CONF_EMAIL, CONF_PASSWORD, CONF_DEVICE_SN, "sn", "serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EcoflowConfigEntry
) -> dict[str, Any]:
    """Liefert Konfiguration und aktuellen Zustand in anonymisierter Form."""
    coordinator = entry.runtime_data
    snapshot = coordinator.data

    return {
        "entry": async_redact_data(dict(entry.data), REDACT),
        "connected": coordinator.connected,
        "snapshot": async_redact_data(asdict(snapshot), REDACT) if snapshot else None,
        # Rohnachrichten je Typ. Das ist der Teil, mit dem sich Geraete
        # unterstuetzen lassen, die diese Integration noch nicht kennt - der
        # Snapshot darueber zeigt nur, was sie ohnehin schon versteht.
        # Seriennummern sind bereits in capture.py entfernt; async_redact_data
        # wuerde einen Hex-String nicht als solche erkennen.
        "capture": coordinator.capture.as_diagnostics(),
    }
