"""Tests der Merge-Logik.

Schwerpunkt ist die Delta-Kodierung: Das Geraet schickt Phasenwerte einzeln
und unvollstaendig. Ein naiver Merge wuerde Werte auf 0 zuruecksetzen.
"""

from __future__ import annotations

import pytest

from custom_components.ecoflow_ocean2.protobuf import (
    DecodedMessage,
    Po2BatteryPack,
    Po2Telemetry,
    decode_mqtt_payload,
)
from custom_components.ecoflow_ocean2.snapshot import (
    average_phases,
    compute_house_load,
    empty_snapshot,
    merge_snapshot,
    sum_phases,
)

SN = "RE11XXXXXXXXXXXX"


def _telemetry(**kwargs) -> DecodedMessage:
    return DecodedMessage(po2_telemetry=Po2Telemetry(**kwargs))


def _merge(*messages: DecodedMessage):
    snapshot = None
    for index, message in enumerate(messages):
        snapshot = merge_snapshot(SN, snapshot, message, now=float(index))
    return snapshot


class TestDeltaKodierung:
    def test_behaelt_vorwerte_wenn_felder_fehlen(self) -> None:
        result = _merge(
            _telemetry(phases={1: {"vol": 235.0, "amp": 1.2, "act_pwr": 280.0}}),
            _telemetry(phases={1: {"act_pwr": 310.0}}),  # nur Wirkleistung
        )
        phase = result.phases["a"]
        assert phase.voltage == 235.0  # erhalten
        assert phase.current == 1.2  # erhalten
        assert phase.active_power == 310.0  # aktualisiert

    def test_nie_empfangene_felder_bleiben_none(self) -> None:
        # Wichtig: keine erfundene 0 - der Sensor wird dann gar nicht gesetzt
        result = _merge(_telemetry(phases={1: {"act_pwr": 100.0}}))
        assert result.phases["a"].voltage is None
        assert result.phases["a"].current is None

    def test_veraendert_vorzustand_nicht(self) -> None:
        first = _merge(_telemetry(phases={1: {"act_pwr": 100.0}}))
        merge_snapshot(SN, first, _telemetry(phases={1: {"act_pwr": 999.0}}), now=9)
        assert first.phases["a"].active_power == 100.0


class TestMehrereNachrichten:
    def test_setzt_werte_nicht_zurueck(self) -> None:
        result = _merge(
            _telemetry(soc_percent=98.0, grid_power_w=0.0, pv_power_w=1127.0),
            _telemetry(pcs_total_w=1069.0),  # nur Wechselrichter-Block
        )
        assert result.battery_soc == 98.0
        assert result.grid_power_w == 0.0
        assert result.inverter_power_w == 1069.0

    def test_ignoriert_soc_platzhalter_null(self) -> None:
        result = _merge(_telemetry(soc_percent=87.0), _telemetry(soc_percent=0.0))
        assert result.battery_soc == 87.0

    def test_mergt_pv_strings_inkrementell(self) -> None:
        result = _merge(
            _telemetry(pv_strings={1: 500.0}),
            _telemetry(pv_strings={2: 600.0}),
        )
        assert result.pv_strings == {1: 500.0, 2: 600.0}

    def test_mergt_batterie_module_ueber_index(self) -> None:
        def pack(index: int, soc: float) -> DecodedMessage:
            return DecodedMessage(
                po2_battery_packs=[
                    Po2BatteryPack(
                        pack_index=index,
                        sn=f"PACK{index}",
                        soc_percent=100.0,
                        real_soc=soc,
                        full_capacity_wh=5024.0,
                        temp_c=38.0,
                        voltage_v=325.8,
                    )
                ]
            )

        result = _merge(pack(1, 99.1), pack(2, 98.7), pack(1, 95.0))
        assert len(result.battery_modules) == 2
        assert result.battery_modules[1].soc == 95.0  # ersetzt, nicht doppelt
        assert result.battery_modules[2].sn == "PACK2"


class TestPhasenSummen:
    def _with_phases(self, phases):
        return _merge(_telemetry(phases=phases))

    def test_summiert_wirkleistung(self) -> None:
        result = self._with_phases(
            {1: {"act_pwr": 100.0}, 2: {"act_pwr": 110.0}, 3: {"act_pwr": 120.0}}
        )
        assert sum_phases(result, "active_power") == 330.0

    def test_null_wenn_eine_phase_fehlt(self) -> None:
        # Teilsumme waere zu niedrig -> lieber nichts anzeigen
        result = self._with_phases(
            {1: {"act_pwr": 100.0}, 2: {"act_pwr": 110.0}, 3: {"react_pwr": 10.0}}
        )
        assert sum_phases(result, "active_power") is None

    def test_funktioniert_einphasig(self) -> None:
        result = self._with_phases({1: {"act_pwr": 1400.0}})
        assert sum_phases(result, "active_power") == 1400.0

    def test_null_ohne_phasen(self) -> None:
        assert sum_phases(empty_snapshot(SN), "active_power") is None

    def test_mittelt_spannung(self) -> None:
        result = self._with_phases(
            {1: {"vol": 235.0}, 2: {"vol": 234.0}, 3: {"vol": 237.0}}
        )
        assert average_phases(result, "voltage") == pytest.approx(235.33, abs=0.01)


class TestHauslast:
    def test_wechselrichter_plus_netz_hat_vorrang(self) -> None:
        """Liegen beide Messwerte vor, wird direkt gerechnet.

        Werte vom 27.07.2026: Der Wechselrichter versorgte das Haus mit
        150,5 W, aus dem Netz kamen 4,2 W - macht 155 W.
        """
        snapshot = empty_snapshot(SN)
        snapshot.inverter_power_w = 150.5
        snapshot.grid_power_w = 4.2
        # Absichtlich widersprechende Werte fuer die alte Bilanz: Sie darf
        # nicht mehr greifen, solange die beiden echten Messwerte da sind.
        snapshot.pv_power_w = 9999.0
        snapshot.battery_power_w = 0.0
        assert round(compute_house_load(snapshot)) == 155

    def test_beim_laden_aus_dem_netz(self) -> None:
        # Wechselrichter zieht 1530 W zum Laden, 1719 W kommen aus dem Netz
        snapshot = empty_snapshot(SN)
        snapshot.inverter_power_w = -1530.0
        snapshot.grid_power_w = 1719.0
        assert round(compute_house_load(snapshot)) == 189

    def test_pv_minus_batterie_plus_netz(self) -> None:
        snapshot = empty_snapshot(SN)
        snapshot.pv_power_w = 1500.0
        snapshot.battery_power_w = -500.0  # entlaedt
        snapshot.grid_power_w = 0.0
        assert compute_house_load(snapshot) == 2000.0

    def test_beruecksichtigt_bezug_und_ladung(self) -> None:
        snapshot = empty_snapshot(SN)
        snapshot.pv_power_w = 1000.0
        snapshot.battery_power_w = 800.0  # laedt
        snapshot.grid_power_w = 300.0
        assert compute_house_load(snapshot) == 500.0

    def test_wird_nie_negativ(self) -> None:
        snapshot = empty_snapshot(SN)
        snapshot.pv_power_w = 100.0
        snapshot.battery_power_w = 900.0
        assert compute_house_load(snapshot) == 0.0

    def test_none_ohne_pv_wert(self) -> None:
        assert compute_house_load(empty_snapshot(SN)) is None


class TestEchtePayload:
    SUMMARY_HEX = (
        "0ac2010a6a3a0f0d00808e441d00808e443500808e448a04440800100018002500e08c442d0080"
        "7f4435004081c43d000000004000480055000000005d0000000060006802700278c04e80010a88"
        "01649001c04e980101a50100000000ba050f0d00c08f441d00c08f443500c08f44106018202001"
        "2801380340fe014827506a580170ada24478fe01800104c20110524531315a453141564a334730"
        "313632ca011052453131585858585858585858585858d20110524531315a453141564a33473031"
        "3632"
    )

    def test_erzeugt_plausiblen_snapshot(self) -> None:
        message = decode_mqtt_payload(bytes.fromhex(self.SUMMARY_HEX))
        assert message.has_payload()
        snapshot = merge_snapshot(SN, None, message, now=1785000000.0)
        assert snapshot.sn == SN
        assert round(snapshot.pv_power_w) == 1127
        assert snapshot.battery_soc == 100
        assert snapshot.battery_remaining_wh == 10048
        # Diese Aufzeichnung enthaelt keinen Wechselrichter-Block, also auch
        # kein Feld 4.13 - ohne das gibt es keinen Netzwert.
        assert snapshot.grid_power_w is None
        # Rueckfallebene greift: PV - Batterie + Netz, mit Batterie und Netz 0
        assert round(snapshot.house_power_w) == 1127
