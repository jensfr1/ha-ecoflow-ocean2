"""EcoFlow PowerOcean - Livedaten ueber das App-MQTT von EcoFlow."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import EcoflowConnectionError
from .const import CONF_DEVICE_SN
from .coordinator import EcoflowCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type EcoflowConfigEntry = ConfigEntry[EcoflowCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EcoflowConfigEntry) -> bool:
    """Richtet eine Anlage ein."""
    coordinator = EcoflowCoordinator(
        hass,
        entry,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        device_sn=entry.data[CONF_DEVICE_SN],
    )

    try:
        await coordinator.async_start()
    except EcoflowConnectionError as err:
        # Home Assistant wiederholt den Setup automatisch mit Backoff
        await coordinator.async_stop()
        raise ConfigEntryNotReady(str(err)) from err
    except Exception:
        await coordinator.async_stop()
        raise

    # Garantiert, dass MQTT-Verbindung und Tasks beim Entladen verschwinden
    entry.async_on_unload(coordinator.async_stop)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EcoflowConfigEntry) -> bool:
    """Entlaedt die Anlage."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
