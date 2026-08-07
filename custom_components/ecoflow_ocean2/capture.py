"""Mitschnitt der Rohnachrichten fuer die Diagnose.

Wer ein Geraet besitzt, das diese Integration noch nicht kennt, kann nur mit
einer Sache helfen: den Nachrichten, die es tatsaechlich sendet. Bis hierher
war das nicht moeglich - der Coordinator verwarf alles stillschweigend, was der
Parser nicht dekodieren konnte, und die Diagnose zeigte nur den fertigen
Snapshot. Also genau die Werte, die schon verstanden werden, und nichts von
dem, woran es fehlt.

Zwei Entscheidungen praegen dieses Modul:

**Ein Beispiel je Nachrichtentyp, nicht die letzten N Nachrichten.** Ein
gemeinsamer Ringpuffer fuellt sich mit dem, was am haeufigsten kommt: Die
Telemetrie trifft im Sekundentakt ein, ein Batterie-Rahmen alle paar Minuten.
Nach kurzer Zeit stuenden dort zwanzig fast gleiche Telemetrie-Rahmen und
nichts sonst - ausgerechnet das Seltene, das eine Anlage von der naechsten
unterscheidet, waere verdraengt.

**Immer an, ohne Schalter.** Der Mitschnitt kostet wenige Kilobyte, und ein
Schalter waere eine Huerde genau fuer die Leute, die helfen wollen: Sie
muessten ihn erst finden, dann einen Tag warten, dann erneut herunterladen.
So genuegt ein Klick auf "Diagnose herunterladen".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .protobuf import iter_frames

#: Befehlspaare, die der Parser auswertet. Alles andere ist ein Fund.
KNOWN: frozenset[tuple[int, int]] = frozenset(
    {(96, 1), (96, 7), (96, 33), (254, 39), (254, 46)}
)

#: Bis hierher wird ein Beispiel aufgehoben. Die bekannten Rahmen liegen bei
#: 200 bis 600 Byte; was darueber hinausgeht, ist zum Verstehen des Aufbaus
#: nicht mehr noetig und blaeht die Diagnosedatei nur auf.
MAX_SAMPLE_BYTES = 1024

#: Mehr Typen als das hat noch kein Geraet gezeigt. Die Grenze verhindert,
#: dass ein defektes Geraet mit wechselnden Befehlspaaren den Speicher fuellt.
MAX_TYPES = 32

#: EcoFlow-Seriennummern sind sechzehn Zeichen aus Grossbuchstaben und Ziffern.
#: Gesucht wird im Byte-Strom, weil sie dort als Klartext stehen - nicht nur
#: die des Geraets selbst, sondern auch die jedes Batteriemoduls.
_SERIAL = re.compile(rb"[A-Z0-9]{16}")


@dataclass
class _Sample:
    """Ein aufgehobener Rahmen samt Zaehler."""

    hex: str
    length: int
    seen: int
    known: bool
    truncated: bool


class FrameCapture:
    """Sammelt je Nachrichtentyp einen geschwaerzten Beispielrahmen."""

    def __init__(self, device_sn: str = "") -> None:
        self._samples: dict[str, _Sample] = {}
        self._device_sn = device_sn.encode("ascii", "ignore")
        #: Nachrichten, aus denen sich nicht ein einziger Rahmen lesen liess.
        self._unparsed = 0
        self._total = 0

    def add(self, raw: bytes) -> None:
        """Nimmt eine rohe MQTT-Payload auf. Wirft nie."""
        self._total += 1
        try:
            frames = iter_frames(raw)
        except Exception:  # noqa: BLE001 - ein defektes Paket darf nichts reissen
            frames = []

        if not frames:
            # Auch das ist ein Befund: Kommt es haeufig vor, spricht das Geraet
            # ein Rahmenformat, das dieser Zerleger gar nicht erst oeffnet.
            self._unparsed += 1
            self._store("unparsed", raw, known=False)
            return

        for frame in frames:
            key = f"{frame.cmd_func}/{frame.cmd_id}"
            self._store(key, frame.pdata, known=(frame.cmd_func, frame.cmd_id) in KNOWN)

    def _store(self, key: str, data: bytes, *, known: bool) -> None:
        existing = self._samples.get(key)
        if existing is not None:
            # Das erste Beispiel bleibt stehen. Es immer wieder zu ersetzen
            # kostet Rechenzeit im Sekundentakt und bringt nichts: Der Aufbau
            # eines Nachrichtentyps aendert sich nicht, nur seine Werte.
            existing.seen += 1
            return
        if len(self._samples) >= MAX_TYPES:
            return
        clipped = data[:MAX_SAMPLE_BYTES]
        self._samples[key] = _Sample(
            hex=self._redact(clipped).hex(),
            length=len(data),
            seen=1,
            known=known,
            truncated=len(data) > MAX_SAMPLE_BYTES,
        )

    def _redact(self, data: bytes) -> bytes:
        """Ersetzt Seriennummern - laengentreu.

        Die Laenge muss stehen bleiben: Ein Protobuf-Rahmen traegt vor jedem
        Feld dessen Laenge, und eine kuerzere Ersetzung wuerde alles danach
        unlesbar machen. Damit waere der Mitschnitt genau fuer den Zweck
        wertlos, fuer den er erhoben wurde.
        """
        if self._device_sn:
            data = data.replace(self._device_sn, b"X" * len(self._device_sn))
        return _SERIAL.sub(lambda m: b"X" * len(m.group()), data)

    def as_diagnostics(self) -> dict[str, Any]:
        """Liefert den Mitschnitt fuer die Diagnosedatei."""
        unknown = sorted(k for k, s in self._samples.items() if not s.known)
        return {
            "messages_seen": self._total,
            "messages_unparsed": self._unparsed,
            # Vorn, weil das die Zeile ist, die jemand zuerst lesen soll:
            # Steht hier etwas, hat das Geraet mehr zu sagen als die
            # Integration versteht.
            "unknown_types": unknown,
            "frames": {
                key: {
                    "seen": s.seen,
                    "known": s.known,
                    "bytes": s.length,
                    "truncated": s.truncated,
                    "sample": s.hex,
                }
                for key, s in sorted(self._samples.items())
            },
        }
