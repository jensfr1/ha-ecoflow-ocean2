"""Binaersensoren der EcoFlow-PowerOcean-Integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcoflowConfigEntry
from .coordinator import EcoflowCoordinator
from .entity import EcoflowEntity
from .snapshot import Snapshot

#: Kleine Leistungen sind Messrauschen bzw. Eigenverbrauch des Geraets und
#: sollen den Zustand nicht dauernd hin- und herschalten lassen.
THRESHOLD_W = 20.0


@dataclass(frozen=True, kw_only=True)
class EcoflowBinaryDescription(BinarySensorEntityDescription):
    """Binaersensor mit Zugriffsfunktion auf den Snapshot."""

    value_fn: Callable[[Snapshot], bool | None]


def _charging(snapshot: Snapshot) -> bool | None:
    if snapshot.battery_power_w is None:
        return None
    return snapshot.battery_power_w > THRESHOLD_W


def _exporting(snapshot: Snapshot) -> bool | None:
    if snapshot.grid_power_w is None:
        return None
    return snapshot.grid_power_w < -THRESHOLD_W


BINARY_SENSORS: tuple[EcoflowBinaryDescription, ...] = (
    EcoflowBinaryDescription(
        key="battery_charging",
        translation_key="battery_charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=_charging,
    ),
    EcoflowBinaryDescription(
        key="grid_exporting",
        translation_key="grid_exporting",
        value_fn=_exporting,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EcoflowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt die Binaersensoren an."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        EcoflowBinarySensor(coordinator, description) for description in BINARY_SENSORS
    ]
    entities.append(EcoflowConnectionSensor(coordinator))
    async_add_entities(entities)


class EcoflowBinarySensor(EcoflowEntity, BinarySensorEntity):
    """Zustand aus dem Snapshot."""

    entity_description: EcoflowBinaryDescription

    def __init__(
        self, coordinator: EcoflowCoordinator, description: EcoflowBinaryDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if not (snapshot := self.coordinator.data):
            return None
        return self.entity_description.value_fn(snapshot)


class EcoflowConnectionSensor(EcoflowEntity, BinarySensorEntity):
    """Zustand der MQTT-Verbindung zur EcoFlow-Cloud.

    Bewusst eine eigene Klasse: Die Basisklasse meldet Entities als *nicht
    verfuegbar*, sobald der Datenstrom abreisst - fuer alle Messwerte richtig,
    fuer diesen Sensor unbrauchbar. Er soll genau dann noch etwas sagen
    koennen, naemlich "getrennt". Sonst laesst sich keine Automation darauf
    bauen, die bei Verbindungsverlust anschlaegt.
    """

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EcoflowCoordinator) -> None:
        super().__init__(coordinator, "connection")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.connected
