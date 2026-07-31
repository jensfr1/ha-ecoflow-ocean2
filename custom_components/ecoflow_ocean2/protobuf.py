"""Protobuf-Decoder fuer EcoFlow-PowerOcean-MQTT-Nachrichten.

Topic: ``/app/device/property/{SN}``

Das Format ist nicht dokumentiert und wurde aus mitgeschnittenem Verkehr
rekonstruiert. Aufbau:

    HeaderMessage { repeated Header header = 1 }
    Header: 1=pdata, 6=enc_type (1 = XOR mit seq & 0xFF), 8=cmd_func,
            9=cmd_id, 14=seq

Nachrichtenklassen:
    cmdFunc 96  - aeltere Generation: 1=EMS-Heartbeat, 7=Batterie-Packs,
                  33=Energiefluss
    cmdFunc 254 - neue Generation (SN ``RE11...``): 39=Telemetrie,
                  46=Batterie-Modul

Bewusst ohne externe Protobuf-Bibliothek: Ein handgeschriebener Wire-Format-
Parser ist hier kleiner und robuster, weil es kein ``.proto``-Schema gibt.
"""

from __future__ import annotations

import base64
import re
import struct
from dataclasses import dataclass, field
from typing import Any

_PRINTABLE = re.compile(r"^[\x20-\x7e]+$")

# Wire-Typen
_VARINT = 0
_FIXED64 = 1
_LENGTH = 2
_FIXED32 = 5


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Liest eine Varint ab ``pos``; gibt (Wert, neue Position) zurueck."""
    result = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        result += (byte & 0x7F) << shift
        if not byte & 0x80:
            break
        shift += 7
    return result, pos


def _decode_fields(data: bytes) -> dict[int, list[Any]]:
    """Zerlegt Protobuf-Bytes in ``{feldnummer: [werte]}``.

    Unbekannte Wire-Typen und abgeschnittene Daten beenden das Parsen
    stillschweigend - der Rest bleibt nutzbar.
    """
    fields: dict[int, list[Any]] = {}
    pos = 0
    size = len(data)

    while pos < size:
        tag, pos = _read_varint(data, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07

        if wire_type == _VARINT:
            value, pos = _read_varint(data, pos)
        elif wire_type == _FIXED64:
            if pos + 8 > size:
                break
            value = struct.unpack_from("<d", data, pos)[0]
            pos += 8
        elif wire_type == _LENGTH:
            length, pos = _read_varint(data, pos)
            if pos + length > size:
                break
            value = data[pos : pos + length]
            pos += length
        elif wire_type == _FIXED32:
            if pos + 4 > size:
                break
            value = struct.unpack_from("<f", data, pos)[0]
            pos += 4
        else:
            break

        fields.setdefault(field_num, []).append(value)

    return fields


def _num(fields: dict[int, list[Any]], num: int, fallback: float = 0.0) -> float:
    """Erster Wert eines Feldes als Zahl."""
    values = fields.get(num)
    if not values:
        return fallback
    value = values[0]
    return float(value) if isinstance(value, (int, float)) else fallback


def _bytes(fields: dict[int, list[Any]], num: int) -> bytes:
    """Erster Wert eines Feldes als Bytes."""
    values = fields.get(num)
    if not values:
        return b""
    value = values[0]
    return value if isinstance(value, bytes) else b""


def _xor_decrypt(pdata: bytes, seq: int) -> bytes:
    """Entschluesselt die Nutzdaten (XOR mit dem untersten Byte von ``seq``)."""
    key = seq & 0xFF
    if key == 0:
        return pdata
    return bytes(b ^ key for b in pdata)


def _decode_sn(raw: bytes) -> str:
    """Seriennummer lesen; manche Geraete liefern sie base64-kodiert."""
    text = raw.decode("utf-8", errors="ignore")
    try:
        decoded = base64.b64decode(text, validate=True).decode("utf-8")
    except Exception:  # noqa: BLE001 - Klartext ist der Normalfall
        return text
    if len(decoded) > 4 and _PRINTABLE.match(decoded):
        return decoded
    return text


# ── Datenstrukturen ──────────────────────────────────────────────────────────


@dataclass
class Phase:
    """Messwerte einer Wechselstromphase."""

    vol: float = 0.0
    amp: float = 0.0
    act_pwr: float = 0.0
    react_pwr: float = 0.0
    apparent_pwr: float = 0.0


@dataclass
class PvString:
    """Messwerte eines MPPT-Strings."""

    vol: float = 0.0
    amp: float = 0.0
    pwr: float = 0.0


@dataclass
class EmsHeartbeat:
    """Wechselrichter-Daten der aelteren Generation (cmdFunc 96 / cmdId 1)."""

    pcs_a_phase: Phase = field(default_factory=Phase)
    pcs_b_phase: Phase = field(default_factory=Phase)
    pcs_c_phase: Phase = field(default_factory=Phase)
    frequency_hz: float = 0.0
    pv_strings: list[PvString] = field(default_factory=list)
    ems_bp_power: float = 0.0
    bp_remain_wh: float = 0.0
    bp_alive_num: float = 0.0


@dataclass
class BatteryPack:
    """Batterie-Modul der aelteren Generation (cmdFunc 96 / cmdId 7)."""

    pack_index: int
    sn: str
    soc: float
    real_soc: float
    soh: float
    pwr: float
    vol: float
    amp: float
    remain_wh: float
    cycles: float
    temp_env: float
    temp_mos: float
    charging: bool


@dataclass
class EnergyStream:
    """Energiefluss der aelteren Generation (cmdFunc 96 / cmdId 33)."""

    sys_load_pwr: float
    sys_grid_pwr: float
    mppt_pwr: float
    bp_pwr: float
    bp_soc: float


@dataclass
class Po2Telemetry:
    """Telemetrie der neuen Generation (cmdFunc 254 / cmdId 39).

    ``None`` heisst: in dieser Nachricht nicht enthalten. Das ist wichtig -
    die Werte kommen verteilt ueber mehrere Nachrichten, und Phasen zusaetzlich
    delta-kodiert.
    """

    pv_power_w: float | None = None
    grid_power_w: float | None = None
    #: Hauslast, wie das Geraet sie selbst meldet (Feld 7.1/87.1).
    house_power_w: float | None = None
    battery_power_w: float | None = None
    soc_percent: float | None = None
    remaining_wh: float | None = None
    pcs_total_w: float | None = None
    # Phasenindex (1-3) -> nur die uebertragenen Felder
    phases: dict[int, dict[str, float]] = field(default_factory=dict)
    # String-Index -> Leistung in W
    pv_strings: dict[int, float] = field(default_factory=dict)


@dataclass
class Po2BatteryPack:
    """Batterie-Modul der neuen Generation (cmdFunc 254 / cmdId 46)."""

    pack_index: int
    sn: str
    soc_percent: float
    real_soc: float
    #: Verbleibende Energie in Wh (Feld 54) - nicht die Kapazitaet
    remaining_wh: float
    temp_c: float
    #: Hoechste Zellspannung in V (Feld 6). Die Packspannung meldet das Geraet nicht.
    cell_voltage_v: float
    #: Modul-Leistung in W: positiv = laden, negativ = entladen
    power_w: float = 0.0
    #: Alterungszustand in %
    soh_percent: float = 0.0
    #: Bisherige Vollzyklen
    cycles: int = 0


@dataclass
class DecodedMessage:
    """Ergebnis einer dekodierten MQTT-Nachricht."""

    energy_stream: EnergyStream | None = None
    ems_heartbeat: EmsHeartbeat | None = None
    battery_packs: list[BatteryPack] = field(default_factory=list)
    po2_telemetry: Po2Telemetry | None = None
    po2_battery_packs: list[Po2BatteryPack] = field(default_factory=list)

    def has_payload(self) -> bool:
        """True, wenn die Nachricht verwertbare Daten enthielt."""
        return bool(
            self.energy_stream
            or self.ems_heartbeat
            or self.po2_telemetry
            or self.battery_packs
            or self.po2_battery_packs
        )


# ── Nachrichtentypen ─────────────────────────────────────────────────────────


def _decode_phase(raw: bytes) -> Phase:
    f = _decode_fields(raw)
    return Phase(
        vol=_num(f, 1),
        amp=_num(f, 2),
        act_pwr=_num(f, 3),
        react_pwr=_num(f, 4),
        apparent_pwr=_num(f, 5),
    )


def _decode_ems_heartbeat(pdata: bytes) -> EmsHeartbeat:
    f = _decode_fields(pdata)

    pv_strings: list[PvString] = []
    for entry_raw in f.get(31, []):
        if not isinstance(entry_raw, bytes):
            continue
        entry = _decode_fields(entry_raw)
        for pv_raw in entry.get(1, []):
            if not isinstance(pv_raw, bytes):
                continue
            pv = _decode_fields(pv_raw)
            pv_strings.append(PvString(vol=_num(pv, 1), amp=_num(pv, 2), pwr=_num(pv, 3)))

    frequency_hz = 0.0
    load_info = _bytes(f, 15)
    if load_info:
        frequency_hz = _num(_decode_fields(load_info), 3)

    return EmsHeartbeat(
        pcs_a_phase=_decode_phase(_bytes(f, 12)) if 12 in f else Phase(),
        pcs_b_phase=_decode_phase(_bytes(f, 13)) if 13 in f else Phase(),
        pcs_c_phase=_decode_phase(_bytes(f, 14)) if 14 in f else Phase(),
        frequency_hz=frequency_hz,
        pv_strings=pv_strings,
        ems_bp_power=_num(f, 59),
        bp_remain_wh=_num(f, 1),
        bp_alive_num=_num(f, 58),
    )


def _decode_battery_packs(pdata: bytes) -> list[BatteryPack]:
    outer = _decode_fields(pdata)
    packs: list[BatteryPack] = []
    for pack_raw in outer.get(1, []):
        if not isinstance(pack_raw, bytes):
            continue
        f = _decode_fields(pack_raw)
        pack_index = int(_num(f, 15))
        if pack_index < 1:
            continue
        packs.append(
            BatteryPack(
                pack_index=pack_index,
                sn=_decode_sn(_bytes(f, 16)),
                soc=_num(f, 2),
                real_soc=_num(f, 38),
                soh=_num(f, 3),
                pwr=_num(f, 1),
                vol=_num(f, 9),
                amp=_num(f, 10),
                remain_wh=_num(f, 54),
                cycles=_num(f, 17),
                temp_env=_num(f, 25),
                temp_mos=_num(f, 19),
                charging=_num(f, 50) == 1,
            )
        )
    return packs


def _decode_energy_stream(pdata: bytes) -> EnergyStream:
    f = _decode_fields(pdata)
    return EnergyStream(
        sys_load_pwr=_num(f, 1),
        sys_grid_pwr=_num(f, 2),
        mppt_pwr=_num(f, 3),
        bp_pwr=_num(f, 4),
        bp_soc=_num(f, 5),
    )


def _decode_po2_telemetry(pdata: bytes) -> Po2Telemetry:
    f = _decode_fields(pdata)
    result = Po2Telemetry()

    # Feld 65 = Systemzusammenfassung.
    #   4  = PV-Leistung
    #   15 = verbleibende Akku-Energie in Wh
    #   17 = System-SoC
    #   20 = Batterieleistung als Betrag
    # ACHTUNG: 65.6 ist NICHT der Netzzaehler, sondern der Wechselrichter-
    # Ausgang. Und 65.7 ist es ebenso wenig - siehe Feld 4.13 weiter unten.
    summary_raw = f.get(65, [None])[0]
    if isinstance(summary_raw, bytes):
        s = _decode_fields(summary_raw)
        result.pv_power_w = _num(s, 4)
        result.soc_percent = _num(s, 17)
        result.remaining_wh = _num(s, 15)
        # Betrag exakt 0 heisst: Akku ruht. Feld 7.4 fehlt dann in den anderen
        # Nachrichten, deshalb hier explizit setzen (Vorzeichen kommt aus 7.4).
        if _num(s, 20) == 0:
            result.battery_power_w = 0.0

    # Feld 7 (bzw. 87) = Energiefluss-Zusammenfassung, so wie die App sie zeigt.
    #   1 = Hauslast
    #   2 = Netzleistung
    #   3 = PV-Leistung
    #   4 = Batterieleistung signiert (negativ = entladen, positiv = laden)
    #
    # Dieser Block ist in sich bilanziert: PV minus Batterie minus Netz ergibt
    # exakt die Hauslast, und alle vier Werte stammen aus demselben Moment. Das
    # unterscheidet ihn von Block 4, dessen Felder einzeln und zu verschiedenen
    # Zeitpunkten aktualisiert werden.
    #
    # Beide Bloecke koennen gleichzeitig auftreten und weichen dann leicht
    # voneinander ab - Block 7 hinkt offenbar einen Messzyklus hinterher, und
    # ihm fehlt haeufiger ein Feld. Deshalb feldweise zusammenfuehren, wobei 87
    # gewinnt: Im Log vom 28.07.2026 meldete Block 7 eine Hauslast von 550 W
    # und Block 87 gleichzeitig 560 W - die App zeigte 560 W.
    #
    # Block 65 bleibt die erste Wahl fuer die PV-Leistung; nur wenn er nichts
    # geliefert hat, springt Block 7/87 ein.
    pv_aus_summary = result.pv_power_w is not None and result.pv_power_w != 0
    for block_nr in (7, 87):
        gen_raw = f.get(block_nr, [None])[0]
        if not isinstance(gen_raw, bytes):
            continue
        g = _decode_fields(gen_raw)
        # Nur setzen, wenn das Feld wirklich da ist - sonst wuerde ein fehlendes
        # Feld einen bereits gelesenen guten Wert mit 0 ueberschreiben.
        if 1 in g:
            result.house_power_w = _num(g, 1)
        # Vorlaeufig; Feld 4.13 weiter unten hat Vorrang, weil es feiner
        # aufgeloest ist und in nahezu jeder Nachricht steckt.
        if 2 in g:
            result.grid_power_w = _num(g, 2)
        if not pv_aus_summary and 3 in g:
            result.pv_power_w = _num(g, 3)
        if 4 in g:
            result.battery_power_w = _num(g, 4)

    # Feld 4 = Wechselrichter-Block.
    #   1    = AC-Gesamtleistung
    #   3.1  = Phasen (delta-kodiert, Index in Unterfeld 6)
    #   13   = Netzleistung
    #   14.1 = PV-Strings (Index in Unterfeld 1, Leistung in 4)
    pcs_raw = f.get(4, [None])[0]
    if isinstance(pcs_raw, bytes):
        p = _decode_fields(pcs_raw)
        if 1 in p:
            result.pcs_total_w = _num(p, 1)

        # 4.13 = Netzleistung, positiv = Bezug, negativ = Einspeisung.
        #
        # Nachgewiesen am 27.07.2026: Beim Laden der Batterie aus dem Netz
        # stand hier 1719 W, waehrend der Wechselrichter (4.1) mit -1530 W zog
        # und das Haus rund 190 W brauchte - die Summe geht auf. Mit dem Ende
        # der Ladung fiel der Wert binnen Sekunden auf 0.
        #
        # Frueher wurde Feld 65.7 verwendet. Das ist eine Einstellung, keine
        # Messung: An einer Anlage mit Nulleinspeisung steht es dauerhaft auf 0
        # (weshalb der Fehler lange unbemerkt blieb), an einer Anlage mit
        # 10-kW-Begrenzung meldete es konstant 10000.
        if 13 in p:
            result.grid_power_w = _num(p, 13)

        phase_block = p.get(3, [None])[0]
        if isinstance(phase_block, bytes):
            for entry_raw in _decode_fields(phase_block).get(1, []):
                if not isinstance(entry_raw, bytes):
                    continue
                e = _decode_fields(entry_raw)
                index = int(_num(e, 6))
                if not 1 <= index <= 3:
                    continue
                phase: dict[str, float] = {}
                if 1 in e:
                    phase["vol"] = _num(e, 1)
                if 2 in e:
                    phase["amp"] = _num(e, 2)
                if 3 in e:
                    phase["act_pwr"] = _num(e, 3)
                if 4 in e:
                    phase["react_pwr"] = _num(e, 4)
                if 5 in e:
                    phase["apparent_pwr"] = _num(e, 5)
                result.phases[index] = phase

        pv_block = p.get(14, [None])[0]
        if isinstance(pv_block, bytes):
            for entry_raw in _decode_fields(pv_block).get(1, []):
                if not isinstance(entry_raw, bytes):
                    continue
                e = _decode_fields(entry_raw)
                index = int(_num(e, 1))
                if index >= 1 and 4 in e:
                    result.pv_strings[index] = _num(e, 4)

    return result


def _decode_po2_battery_pack(pdata: bytes) -> Po2BatteryPack | None:
    f = _decode_fields(pdata)
    pack_raw = f.get(5, [None])[0]
    if not isinstance(pack_raw, bytes):
        return None
    p = _decode_fields(pack_raw)
    pack_index = int(_num(p, 15))
    if pack_index < 1:
        return None
    # Korrigiert am 31.07.2026 nach einem Hinweis von Sebastian
    # (ecoflow-energy-ha) und an der laufenden Anlage nachgemessen:
    #
    #   54  ist die Restenergie, NICHT die volle Kapazitaet. Gemessen 4114 Wh
    #       bei 81,5 % und 4137 Wh bei 82,0 % - macht rund 5046 Wh Vollkapazitaet.
    #       Als Kapazitaet gelesen sinkt der Wert beim Entladen; am Schreibtisch
    #       faellt das nicht auf, im Betrieb ist es dauerhaft irrefuehrend.
    #   39  ist der SoH, nicht der SoC: ueber die gesamte Messung konstant 100,0,
    #       waehrend 38 sich bewegte. Das Paar 38/39 spiegelt 2/3.
    #    6  ist eine Zellspannung (3329 mV), keine Packspannung - sie folgt der
    #       Last. Das Teilen durch 10 war schon ein Warnzeichen: Ein float
    #       braucht keine Skalierung.
    #
    # Die Packspannung liegt in keinem beobachteten Feld und wird deshalb gar
    # nicht mehr gemeldet, statt einen falschen Wert auszuweisen.
    return Po2BatteryPack(
        pack_index=pack_index,
        sn=_bytes(p, 16).decode("utf-8", errors="ignore"),
        soc_percent=_num(p, 38),
        real_soc=_num(p, 38),
        remaining_wh=_num(p, 54),
        temp_c=_num(p, 21),
        cell_voltage_v=_num(p, 6) / 1000,
        # 1/3/17 tragen dieselbe Bedeutung wie bei der aelteren Generation -
        # geprueft am 28.07.2026: 1122,59 W / 100 % / 4 Zyklen an einem vier
        # Wochen alten System.
        power_w=_num(p, 1),
        soh_percent=_num(p, 3),
        cycles=int(_num(p, 17)),
    )


def decode_mqtt_payload(raw: bytes) -> DecodedMessage:
    """Dekodiert eine rohe MQTT-Payload.

    Wirft nicht: Unbekannte oder beschaedigte Nachrichten ergeben ein leeres
    Ergebnis (``has_payload() is False``).
    """
    result = DecodedMessage()
    outer = _decode_fields(raw)

    for header_raw in outer.get(1, []):
        if not isinstance(header_raw, bytes):
            continue
        h = _decode_fields(header_raw)
        cmd_func = int(_num(h, 8))
        cmd_id = int(_num(h, 9))
        enc_type = int(_num(h, 6))
        seq = int(_num(h, 14))

        pdata = _bytes(h, 1)
        if not pdata:
            continue
        if enc_type == 1:
            pdata = _xor_decrypt(pdata, seq)

        if cmd_func == 96:
            if cmd_id == 1:
                result.ems_heartbeat = _decode_ems_heartbeat(pdata)
            elif cmd_id == 7:
                result.battery_packs.extend(_decode_battery_packs(pdata))
            elif cmd_id == 33:
                result.energy_stream = _decode_energy_stream(pdata)
        elif cmd_func == 254:
            if cmd_id == 39:
                result.po2_telemetry = _decode_po2_telemetry(pdata)
            elif cmd_id == 46:
                pack = _decode_po2_battery_pack(pdata)
                if pack:
                    result.po2_battery_packs.append(pack)

    return result
