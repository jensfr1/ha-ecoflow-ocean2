"""Sensoren der EcoFlow-PowerOcean-Integration."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcoflowConfigEntry
from .coordinator import EcoflowCoordinator
from .energy import EnergyIntegrator, negative, positive
from .entity import EcoflowEntity, EcoflowModuleEntity
from .snapshot import Snapshot, average_phases, sum_phases


@dataclass(frozen=True, kw_only=True)
class EcoflowSensorDescription(SensorEntityDescription):
    """Sensor mit Zugriffsfunktion auf den Snapshot."""

    value_fn: Callable[[Snapshot], float | None]


def _phase(key: str, attribute: str) -> Callable[[Snapshot], float | None]:
    def getter(snapshot: Snapshot) -> float | None:
        phase = snapshot.phases.get(key)
        return getattr(phase, attribute) if phase else None

    return getter


POWER = {
    "device_class": SensorDeviceClass.POWER,
    "native_unit_of_measurement": UnitOfPower.WATT,
    "state_class": SensorStateClass.MEASUREMENT,
    "suggested_display_precision": 0,
}

SENSORS: tuple[EcoflowSensorDescription, ...] = (
    EcoflowSensorDescription(
        key="pv_power", translation_key="pv_power", value_fn=lambda s: s.pv_power_w, **POWER
    ),
    EcoflowSensorDescription(
        key="battery_power",
        translation_key="battery_power",
        value_fn=lambda s: s.battery_power_w,
        **POWER,
    ),
    EcoflowSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        value_fn=lambda s: s.grid_power_w,
        **POWER,
    ),
    EcoflowSensorDescription(
        key="house_power",
        translation_key="house_power",
        value_fn=lambda s: s.house_power_w,
        **POWER,
    ),
    EcoflowSensorDescription(
        key="inverter_power",
        translation_key="inverter_power",
        value_fn=lambda s: s.inverter_power_w,
        entity_registry_enabled_default=False,
        **POWER,
    ),
    EcoflowSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.battery_soc,
    ),
    EcoflowSensorDescription(
        key="battery_remaining_energy",
        translation_key="battery_remaining_energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda s: s.battery_remaining_wh,
    ),
    EcoflowSensorDescription(
        key="phases_total_active_power",
        translation_key="phases_total_active_power",
        value_fn=lambda s: sum_phases(s, "active_power"),
        **POWER,
    ),
    EcoflowSensorDescription(
        key="phases_average_voltage",
        translation_key="phases_average_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda s: average_phases(s, "voltage"),
    ),
)

# Je Phase Spannung, Strom und Wirkleistung. Standardmaessig deaktiviert -
# die meisten Nutzer brauchen nur die Summe, und 9 zusaetzliche Entities
# ueberfrachten sonst die Geraeteseite.
PHASE_SENSORS: tuple[EcoflowSensorDescription, ...] = tuple(
    description
    for key in ("a", "b", "c")
    for description in (
        EcoflowSensorDescription(
            key=f"phase_{key}_voltage",
            translation_key=f"phase_{key}_voltage",
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            entity_registry_enabled_default=False,
            value_fn=_phase(key, "voltage"),
        ),
        EcoflowSensorDescription(
            key=f"phase_{key}_current",
            translation_key=f"phase_{key}_current",
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            entity_registry_enabled_default=False,
            value_fn=_phase(key, "current"),
        ),
        EcoflowSensorDescription(
            key=f"phase_{key}_active_power",
            translation_key=f"phase_{key}_active_power",
            entity_registry_enabled_default=False,
            value_fn=_phase(key, "active_power"),
            **POWER,
        ),
    )
)


@dataclass(frozen=True, kw_only=True)
class EcoflowEnergyDescription(SensorEntityDescription):
    """Energiezaehler, der aus einer Leistung integriert wird."""

    power_fn: Callable[[Snapshot], float | None]


ENERGY = {
    "device_class": SensorDeviceClass.ENERGY,
    "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
    "suggested_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    "suggested_display_precision": 2,
}

ENERGY_SENSORS: tuple[EcoflowEnergyDescription, ...] = (
    EcoflowEnergyDescription(
        key="pv_produced_energy",
        translation_key="pv_produced_energy",
        power_fn=lambda s: s.pv_power_w,
        **ENERGY,
    ),
    EcoflowEnergyDescription(
        key="grid_imported_energy",
        translation_key="grid_imported_energy",
        power_fn=lambda s: positive(s.grid_power_w),
        **ENERGY,
    ),
    EcoflowEnergyDescription(
        key="grid_exported_energy",
        translation_key="grid_exported_energy",
        power_fn=lambda s: negative(s.grid_power_w),
        **ENERGY,
    ),
    EcoflowEnergyDescription(
        key="battery_charged_energy",
        translation_key="battery_charged_energy",
        power_fn=lambda s: positive(s.battery_power_w),
        **ENERGY,
    ),
    EcoflowEnergyDescription(
        key="battery_discharged_energy",
        translation_key="battery_discharged_energy",
        power_fn=lambda s: negative(s.battery_power_w),
        **ENERGY,
    ),
    EcoflowEnergyDescription(
        key="house_consumed_energy",
        translation_key="house_consumed_energy",
        power_fn=lambda s: s.house_power_w,
        **ENERGY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EcoflowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt die Sensoren an."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        EcoflowSensor(coordinator, description)
        for description in (*SENSORS, *PHASE_SENSORS)
    ]
    entities += [
        EcoflowEnergySensor(coordinator, description) for description in ENERGY_SENSORS
    ]

    async_add_entities(entities)

    # ── Nachwachsende Entities ───────────────────────────────────────────────
    #
    # Batteriemodule und PV-Straenge stehen beim Einrichten noch nicht fest:
    # Der Zustand ist dann leer, weil die erste MQTT-Nachricht erst Sekunden
    # spaeter eintrifft. Wer sie nur hier anlegt, bekommt beim ersten Start
    # ueberhaupt keine Modulsensoren - bis die Integration neu geladen wird.
    #
    # Deshalb hoeren wir dem Coordinator zu und legen nach, sobald ein neuer
    # Index auftaucht. Das deckt auch den Fall ab, dass jemand spaeter ein
    # Modul ergaenzt oder ein Strang erst bei Sonnenschein meldet.
    bekannte_module: set[int] = set()
    bekannte_straenge: set[int] = set()

    @callback
    def _pruefe_neue_geraete() -> None:
        if not (snapshot := coordinator.data):
            return
        neue: list[SensorEntity] = []

        for index in sorted(set(snapshot.battery_modules) - bekannte_module):
            bekannte_module.add(index)
            neue += [
                EcoflowModuleSensor(coordinator, index, measure)
                for measure in EcoflowModuleSensor.MEASURE_KEYS
            ]

        for index in sorted(set(snapshot.pv_strings) - bekannte_straenge):
            bekannte_straenge.add(index)
            neue.append(EcoflowPvStringSensor(coordinator, index))

        if neue:
            async_add_entities(neue)

    entry.async_on_unload(coordinator.async_add_listener(_pruefe_neue_geraete))
    _pruefe_neue_geraete()


class EcoflowSensor(EcoflowEntity, SensorEntity):
    """Messwert aus dem Snapshot."""

    entity_description: EcoflowSensorDescription

    def __init__(
        self, coordinator: EcoflowCoordinator, description: EcoflowSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        if not (snapshot := self.coordinator.data):
            return None
        return self.entity_description.value_fn(snapshot)


class EcoflowEnergySensor(EcoflowEntity, RestoreSensor):
    """Zaehler, der die Leistung ueber die Zeit aufsummiert."""

    entity_description: EcoflowEnergyDescription

    def __init__(
        self, coordinator: EcoflowCoordinator, description: EcoflowEnergyDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._integrator = EnergyIntegrator()

    @property
    def available(self) -> bool:
        """Zaehler bleiben verfuegbar, auch wenn die Verbindung kurz weg ist.

        Ein Zaehlerstand veraltet nicht - im Gegensatz zu einem Leistungswert.
        Waere er kurzzeitig 'unavailable', entstuenden Luecken im Dashboard.
        """
        return True

    async def async_added_to_hass(self) -> None:
        """Stellt den Zaehlerstand nach einem Neustart wieder her."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) and last.native_value is not None:
            try:
                self._integrator.restore(float(last.native_value))
            except (TypeError, ValueError):
                pass

    @callback
    def _handle_coordinator_update(self) -> None:
        if snapshot := self.coordinator.data:
            power = self.entity_description.power_fn(snapshot)
            self._integrator.add(power, time.monotonic())
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        return round(self._integrator.total_wh, 3)


class EcoflowPvStringSensor(EcoflowEntity, SensorEntity):
    """Leistung eines einzelnen MPPT-Strings."""

    _attr_translation_key = "pv_string_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: EcoflowCoordinator, index: int) -> None:
        super().__init__(coordinator, f"pv_string_{index}_power")
        self._index = index
        self._attr_translation_placeholders = {"index": str(index)}

    @property
    def native_value(self) -> float | None:
        if not (snapshot := self.coordinator.data):
            return None
        return snapshot.pv_strings.get(self._index)


class EcoflowModuleSensor(EcoflowModuleEntity, SensorEntity):
    """Messwert eines Batteriemoduls."""

    #: Reihenfolge, in der die Sensoren je Modul angelegt werden.
    MEASURE_KEYS = (
        "soc",
        "temperature",
        "cell_voltage",
        "remaining_energy",
        "power",
        "soh",
        "cycles",
    )

    #: Messgroesse -> (Geraeteklasse, Einheit, Nachkommastellen, Feld im Snapshot)
    _MEASURES = {
        "soc": (SensorDeviceClass.BATTERY, PERCENTAGE, 1, "soc"),
        "temperature": (
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            1,
            "temperature",
        ),
        # Hoechste Zellspannung, nicht die Packspannung - die meldet das
        # Ocean 2 in keinem beobachteten Feld. Drei Nachkommastellen, weil
        # sich hier alles im Millivoltbereich abspielt.
        "cell_voltage": (
            SensorDeviceClass.VOLTAGE,
            UnitOfElectricPotential.VOLT,
            3,
            "cell_voltage",
        ),
        "remaining_energy": (
            SensorDeviceClass.ENERGY_STORAGE,
            UnitOfEnergy.WATT_HOUR,
            0,
            "remaining_wh",
        ),
        "power": (SensorDeviceClass.POWER, UnitOfPower.WATT, 0, "power_w"),
        # Alterungszustand: bewusst ohne Geraeteklasse. BATTERY waere der
        # Ladestand und wuerde in der Oberflaeche als solcher dargestellt.
        "soh": (None, PERCENTAGE, 1, "soh_percent"),
        "cycles": (None, None, 0, "cycles"),
    }

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EcoflowCoordinator, index: int, measure: str) -> None:
        super().__init__(coordinator, f"module_{index}_{measure}", index)
        self._measure = measure
        device_class, unit, precision, self._attribute = self._MEASURES[measure]
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_suggested_display_precision = precision
        self._attr_translation_key = f"module_{measure}"
        self._attr_translation_placeholders = {"index": str(index)}

    @property
    def native_value(self) -> float | None:
        if not (snapshot := self.coordinator.data):
            return None
        if not (module := snapshot.battery_modules.get(self._index)):
            return None
        return getattr(module, self._attribute)
