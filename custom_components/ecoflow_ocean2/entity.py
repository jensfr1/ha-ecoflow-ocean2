"""Gemeinsame Basis der Entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import EcoflowCoordinator


class EcoflowEntity(CoordinatorEntity[EcoflowCoordinator]):
    """Basis: Geraetezuordnung und ehrliche Verfuegbarkeit."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EcoflowCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_sn}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_sn)},
            name="PowerOcean",
            manufacturer=MANUFACTURER,
            model=MODEL,
            serial_number=coordinator.device_sn,
        )

    @property
    def available(self) -> bool:
        """Nicht verfuegbar, sobald der Datenstrom abreisst.

        Sonst wuerden veraltete Werte als aktuell erscheinen - gerade bei
        Leistungsdaten waere das irrefuehrend.
        """
        return super().available and self.coordinator.connected


class EcoflowModuleEntity(EcoflowEntity):
    """Entity eines einzelnen Batteriemoduls (eigenes Untergeraet)."""

    def __init__(self, coordinator: EcoflowCoordinator, key: str, index: int) -> None:
        super().__init__(coordinator, key)
        self._index = index
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.device_sn}_module{index}")},
            name=f"Battery module {index}",
            manufacturer=MANUFACTURER,
            model=f"{MODEL} Battery",
            via_device=(DOMAIN, coordinator.device_sn),
        )
