"""Mitschnitt der Rohnachrichten.

Die Rahmen werden hier gebaut statt aus einer Aufzeichnung gelesen: Ein echter
Rahmen traegt die Seriennummer, und der Mitschnitt soll ja gerade zeigen, dass
sie verschwindet.
"""

from __future__ import annotations

import struct

from custom_components.ecoflow_ocean2.capture import (
    MAX_SAMPLE_BYTES,
    MAX_TYPES,
    FrameCapture,
)

SN = "RE11ZQH4SF001234"


def _varint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _msg(field: int, body: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(body)) + body


def _vint(field: int, value: int) -> bytes:
    return _varint((field << 3) | 0) + _varint(value)


def _f32(field: int, value: float) -> bytes:
    return _varint((field << 3) | 5) + struct.pack("<f", value)


def frame(cmd_func: int, cmd_id: int, pdata: bytes) -> bytes:
    """Eine Nachricht mit genau einem Rahmen."""
    return _msg(1, _msg(1, pdata) + _vint(8, cmd_func) + _vint(9, cmd_id))


def bundle(*parts: tuple[int, int, bytes]) -> bytes:
    """Mehrere Rahmen in einer Nachricht - so sendet das Geraet wirklich."""
    out = b""
    for cmd_func, cmd_id, pdata in parts:
        out += _msg(1, _msg(1, pdata) + _vint(8, cmd_func) + _vint(9, cmd_id))
    return out


class TestErfassung:
    def test_haelt_je_nachrichtentyp_ein_beispiel_fest(self) -> None:
        c = FrameCapture(SN)
        c.add(frame(254, 39, _f32(1, 100.0)))
        c.add(frame(254, 46, _f32(1, 200.0)))
        d = c.as_diagnostics()
        assert set(d["frames"]) == {"254/39", "254/46"}

    def test_zaehlt_wiederholungen_statt_sie_zu_speichern(self) -> None:
        # Der Aufbau eines Typs aendert sich nicht, nur seine Werte - ein
        # Beispiel genuegt, die Haeufigkeit ist die eigentliche Information.
        c = FrameCapture(SN)
        for _ in range(50):
            c.add(frame(254, 39, _f32(1, 100.0)))
        d = c.as_diagnostics()
        assert d["frames"]["254/39"]["seen"] == 50
        assert len(d["frames"]) == 1

    def test_haeufiger_typ_verdraengt_seltenen_nicht(self) -> None:
        # Der eigentliche Zweck: Die Telemetrie kommt im Sekundentakt, der
        # Batterierahmen alle paar Minuten. Ein gemeinsamer Ringpuffer haette
        # nach kurzer Zeit nur noch Telemetrie.
        c = FrameCapture(SN)
        c.add(frame(254, 46, _f32(1, 200.0)))
        for _ in range(500):
            c.add(frame(254, 39, _f32(1, 100.0)))
        assert "254/46" in c.as_diagnostics()["frames"]

    def test_zerlegt_gebuendelte_rahmen_einzeln(self) -> None:
        c = FrameCapture(SN)
        c.add(bundle((254, 39, _f32(1, 1.0)), (254, 46, _f32(1, 2.0))))
        assert set(c.as_diagnostics()["frames"]) == {"254/39", "254/46"}


class TestUnbekannteTypen:
    def test_meldet_was_der_parser_nicht_auswertet(self) -> None:
        # Der Fund, um den es geht: ein Geraet sendet mehr, als hier bekannt ist.
        c = FrameCapture(SN)
        c.add(frame(254, 39, _f32(1, 100.0)))
        c.add(frame(36, 2, _f32(1, 100.0)))
        d = c.as_diagnostics()
        assert d["unknown_types"] == ["36/2"]
        assert d["frames"]["254/39"]["known"] is True
        assert d["frames"]["36/2"]["known"] is False

    def test_haelt_auch_voellig_unlesbare_nachrichten_fest(self) -> None:
        c = FrameCapture(SN)
        c.add(b"\xff\xfe kein protobuf")
        d = c.as_diagnostics()
        assert d["messages_unparsed"] == 1
        assert "unparsed" in d["frames"]

    def test_zaehlt_alle_nachrichten_mit(self) -> None:
        c = FrameCapture(SN)
        c.add(frame(254, 39, _f32(1, 1.0)))
        c.add(b"\xff\xfe")
        assert c.as_diagnostics()["messages_seen"] == 2


class TestSchwaerzung:
    def test_entfernt_die_seriennummer_des_geraets(self) -> None:
        c = FrameCapture(SN)
        c.add(frame(254, 46, _msg(16, SN.encode())))
        sample = c.as_diagnostics()["frames"]["254/46"]["sample"]
        assert SN.encode().hex() not in sample

    def test_entfernt_auch_unbekannte_seriennummern(self) -> None:
        # Die Module tragen eigene Nummern, die niemand vorher kennt.
        fremd = "BP5000ABCD001234"
        c = FrameCapture(SN)
        c.add(frame(254, 46, _msg(16, fremd.encode())))
        sample = c.as_diagnostics()["frames"]["254/46"]["sample"]
        assert fremd.encode().hex() not in sample

    def test_schwaerzt_laengentreu(self) -> None:
        # Entscheidend: Protobuf traegt vor jedem Feld dessen Laenge. Eine
        # kuerzere Ersetzung machte alles danach unlesbar - und damit den
        # Mitschnitt wertlos fuer genau den Zweck, fuer den er erhoben wurde.
        pdata = _msg(16, SN.encode()) + _f32(1, 42.0)
        c = FrameCapture(SN)
        c.add(frame(254, 46, pdata))
        d = c.as_diagnostics()["frames"]["254/46"]
        assert len(bytes.fromhex(d["sample"])) == len(pdata)
        # Der Wert hinter der Seriennummer muss noch dekodierbar sein
        assert _f32(1, 42.0).hex() in d["sample"]

    def test_kommt_ohne_bekannte_seriennummer_aus(self) -> None:
        c = FrameCapture()
        c.add(frame(254, 46, _msg(16, SN.encode())))
        assert SN.encode().hex() not in c.as_diagnostics()["frames"]["254/46"]["sample"]


class TestGrenzen:
    def test_kuerzt_uebergrosse_rahmen_und_sagt_es(self) -> None:
        c = FrameCapture(SN)
        c.add(frame(254, 39, b"\x08" * (MAX_SAMPLE_BYTES * 2)))
        d = c.as_diagnostics()["frames"]["254/39"]
        assert d["truncated"] is True
        assert d["bytes"] == MAX_SAMPLE_BYTES * 2
        assert len(bytes.fromhex(d["sample"])) == MAX_SAMPLE_BYTES

    def test_nimmt_nicht_beliebig_viele_typen_auf(self) -> None:
        # Ein defektes Geraet mit wechselnden Befehlspaaren darf den Speicher
        # nicht fuellen.
        c = FrameCapture(SN)
        for i in range(MAX_TYPES + 20):
            c.add(frame(200, i, _f32(1, 1.0)))
        assert len(c.as_diagnostics()["frames"]) == MAX_TYPES

    def test_wirft_bei_muell_niemals(self) -> None:
        c = FrameCapture(SN)
        for payload in (b"", b"\x00", b"\x0a", b"\x0a\xff\xff", bytes(range(256))):
            c.add(payload)
        assert c.as_diagnostics()["messages_seen"] == 5
