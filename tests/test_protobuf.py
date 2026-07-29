"""Tests des Protobuf-Decoders gegen echte, aufgezeichnete Payloads.

Die Erwartungswerte stammen aus der TypeScript-Referenzimplementierung
(ioBroker-Adapter), die gegen das EcoFlow-Webportal verifiziert wurde.
Weichen diese Tests ab, ist die Portierung fehlerhaft.
"""

from __future__ import annotations

import pytest

from custom_components.ecoflow_ocean2.protobuf import decode_mqtt_payload

# Aufgezeichnet vom Topic /app/device/property/RE11XXXXXXXXXXXX (PowerOcean,
# neue Generation, 2026-07-25). Beide sind cmdFunc 254 / cmdId 39, aber
# unterschiedliche Untertypen.
PCS_BLOCK_HEX = (
    "0ad6010a7e22590d78a085441a390a111d183aab4325fe59cb422d529db24330010a111db8fcad43"
    "25e2c6b4422dd8c2b34330020a111d67e8b2432583b8b7422da0b5b84330036dc0cee24172120a07"
    "080125df9209440a070802255f6a18443a0f0d00408d441d00408d443500408d44ba050f0d00408d"
    "441d00408d443500408d441060182020012801380340fe014827507e580170caa24478fe01800104"
    "c2011052453131585858585858585858585858ca011052453131585858585858585858585858d201"
    "1052453131585858585858585858585858"
)

SUMMARY_HEX = (
    "0ac2010a6a3a0f0d00808e441d00808e443500808e448a04440800100018002500e08c442d00807f"
    "4435004081c43d000000004000480055000000005d0000000060006802700278c04e80010a880164"
    "9001c04e980101a50100000000ba050f0d00c08f441d00c08f443500c08f44106018202001280138"
    "0340fe014827506a580170ada24478fe01800104c20110524531315858585858585858585858586"
    "3ca011052453131585858585858585858585858d2011052453131585858585858585858585858"
)


def _hex(value: str) -> bytes:
    return bytes.fromhex(value)


@pytest.fixture(name="summary")
def summary_fixture():
    return decode_mqtt_payload(_hex(SUMMARY_HEX))


@pytest.fixture(name="pcs")
def pcs_fixture():
    return decode_mqtt_payload(_hex(PCS_BLOCK_HEX))


class TestSummary:
    """Feld 65 - Systemzusammenfassung."""

    def test_erkennt_telemetrie(self, summary) -> None:
        assert summary.po2_telemetry is not None
        assert summary.has_payload()

    def test_liest_pv_batterie_soc(self, summary) -> None:
        t = summary.po2_telemetry
        assert round(t.pv_power_w) == 1127
        assert t.battery_power_w == 0
        assert t.soc_percent == 100

    def test_ohne_wechselrichterblock_keine_netzleistung(self, summary) -> None:
        """Diese Aufzeichnung enthaelt nur Block 65, also kein Feld 4.13.

        Frueher wurde hier 65.7 als Netzleistung gelesen; das ergab 0 und sah
        plausibel aus, ist aber eine Einstellung und keine Messung. Ohne
        Block 4 gibt es schlicht keinen Netzwert - None ist die ehrliche
        Antwort darauf.
        """
        assert summary.po2_telemetry.grid_power_w is None

    def test_liest_verbleibende_energie(self, summary) -> None:
        # 10048 Wh entspricht dem 10-kWh-Speicher
        assert summary.po2_telemetry.remaining_wh == 10048


class TestPcsBlock:
    """Feld 4 - Wechselrichter-Block."""

    def test_liest_pv_und_wechselrichter_leistung(self, pcs) -> None:
        t = pcs.po2_telemetry
        assert round(t.pv_power_w) == 1130
        assert round(t.pcs_total_w) == 1069

    def test_liest_alle_drei_phasen(self, pcs) -> None:
        phases = pcs.po2_telemetry.phases
        assert sorted(phases) == [1, 2, 3]
        assert round(phases[1]["act_pwr"]) == 342
        assert round(phases[2]["act_pwr"]) == 348
        assert round(phases[3]["act_pwr"]) == 358

    def test_phasen_sind_delta_kodiert(self, pcs) -> None:
        # Spannung und Strom fehlen in dieser Nachricht bewusst. Der Merge muss
        # deshalb Vorwerte behalten statt auf 0 zurueckzusetzen.
        phase_a = pcs.po2_telemetry.phases[1]
        assert "act_pwr" in phase_a
        assert "vol" not in phase_a
        assert "amp" not in phase_a

    def test_liest_pv_strings(self, pcs) -> None:
        strings = pcs.po2_telemetry.pv_strings
        assert round(strings[1]) == 550
        assert round(strings[2]) == 610


class TestRobustheit:
    """Beschaedigte Eingaben duerfen die Integration nicht abschiessen."""

    @pytest.mark.parametrize(
        "payload",
        [
            b"",
            bytes.fromhex(SUMMARY_HEX)[:40],
            bytes(range(0, 256, 4)),
            b"\xff" * 32,
        ],
        ids=["leer", "abgeschnitten", "zufall", "nur-ff"],
    )
    def test_wirft_nicht(self, payload: bytes) -> None:
        result = decode_mqtt_payload(payload)
        assert result is not None

    def test_unbekannte_nachricht_ist_leer(self) -> None:
        # Gueltiger Envelope, aber cmdFunc/cmdId, die wir nicht kennen
        assert not decode_mqtt_payload(b"\x0a\x04\x0a\x02\x01\x02").has_payload()


class TestNetzleistung:
    """Feld 4.13 - die tatsaechliche Netzleistung.

    Aufgezeichnet am 27.07.2026 an der Referenzanlage. Der Frame enthaelt
    Block 4 mit Wechselrichter- und Netzwert; daran laesst sich die Hauslast
    gegenrechnen.
    """

    HEX = (
        "0a93010a3a22380dec7e16431a210a111dc4524c42255284d5422df8b2ec4230010a0c1d8de86342251624d14230036d8051874072090a070802150281d2421060182020012801380340fe014827503a58017090eff90178fe01800104c2011052453131585858585858585858585858ca011052453131585858585858585858585858d2011052453131585858585858585858585858"
    )

    def test_liest_netz_und_wechselrichter(self) -> None:
        message = decode_mqtt_payload(bytes.fromhex(self.HEX))
        t = message.po2_telemetry
        assert t is not None
        assert round(t.grid_power_w, 1) == 4.2
        assert round(t.pcs_total_w, 1) == 150.5


class TestHauslast:
    """Feld 7.1/87.1 - die Hauslast, wie das Geraet sie selbst meldet.

    Aufgezeichnet am 28.07.2026 an einer dreiphasigen Anlage mit zwei Modulen
    (Seriennummern anonymisiert). Der Frame belegt, warum die Hauslast gemessen
    und nicht gerechnet gehoert: Block 87 meldet 490 W und bilanziert sauber
    (PV 2570 - Batterie 310 - Einspeisung 1770 = 490), waehrend Wechselrichter
    plus Netz aus Block 4 nur 306 W ergeben - diese beiden Felder stammen aus
    verschiedenen Momenten.

    Der Frame traegt Block 7 und Block 87 gleichzeitig mit leicht abweichenden
    Werten. Block 87 gewinnt; die App zeigte dessen Zahlen.
    """

    HEX = (
        "0af6010a9b01225a0d73060e451a390a111dad563744258eebe2422d1485394430010a111d077f374425a695c7422d352f394430020a111dd60b374425b929cf422d6ede384430032d426557446d3bccf5c4720e0a0c0802157b62c84325e079bc443a14150000e1c41d00e021452500009b433500e0214582040a0d224599431504bcb745ba05190d0000f543150040ddc41d00a020452500009b433500a020451060182020012801380340fe014827509b01580170d3d5be0578fe01800104c2011052453131585858585858585858585858ca011052453131585858585858585858585858d2011052453131585858585858585858585858"
    )

    def test_nimmt_gemeldete_hauslast_nicht_die_rechnung(self) -> None:
        t = decode_mqtt_payload(bytes.fromhex(self.HEX)).po2_telemetry
        assert t is not None
        assert t.house_power_w == 490
        # Was die alte Rechnung ergeben haette - deutlich daneben
        assert round(t.pcs_total_w + t.grid_power_w) == 306

    def test_bilanziert_mit_pv_batterie_und_netz(self) -> None:
        t = decode_mqtt_payload(bytes.fromhex(self.HEX)).po2_telemetry
        assert t is not None
        assert t.pv_power_w == 2570
        assert t.battery_power_w == 310
        assert t.pv_power_w - t.battery_power_w - 1770 == t.house_power_w

    def test_feld_4_13_hat_vorrang_vor_7_2(self) -> None:
        t = decode_mqtt_payload(bytes.fromhex(self.HEX)).po2_telemetry
        assert t is not None
        assert round(t.grid_power_w, 1) == -1966.4

    def test_ohne_block_7_bleibt_hauslast_leer(self) -> None:
        t = decode_mqtt_payload(bytes.fromhex(TestNetzleistung.HEX)).po2_telemetry
        assert t is not None
        assert t.house_power_w is None
