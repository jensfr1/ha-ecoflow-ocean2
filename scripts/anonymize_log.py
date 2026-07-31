#!/usr/bin/env python3
"""Entfernt Seriennummern aus einem Home-Assistant-Protokoll.

Die Rohframes enthalten die Seriennummer gleich doppelt: als lesbaren Text in
der Logzeile und hexadezimal kodiert innerhalb des Frames. Beides muss weg,
bevor ein Mitschnitt in ein oeffentliches Issue wandert.

Entscheidend ist, dass der Ersatz **genauso lang** ist wie das Original. Die
Frames sind laengenkodiert - ein kuerzerer Platzhalter verschiebt alle
folgenden Bytes, und der Mitschnitt waere wertlos.

Aufruf:
    python scripts/anonymize_log.py home-assistant.log > mitschnitt.txt
    python scripts/anonymize_log.py home-assistant.log --alle > alles.txt

Ohne --alle bleiben nur die Zeilen mit Rohframes uebrig; das kuerzt ein
Tagesprotokoll von hunderten Megabyte auf das, worum es geht.
"""

from __future__ import annotations

import argparse
import re
import sys

#: EcoFlow-Seriennummern: zwei Buchstaben, dann Ziffern und Grossbuchstaben.
#: Die Laenge von 16 Zeichen ist bei allen bisher gesehenen Geraeten gleich
#: (Wechselrichter RE11..., Batteriemodule RE12...).
SN_MUSTER = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{12})\b")

#: Dieselbe Seriennummer, hex-kodiert im Frame. Jedes Zeichen wird zu zwei
#: Hex-Ziffern, gesucht wird also die Kodierung von "RE" bzw. "HJ" gefolgt von
#: 14 weiteren Zeichen.
SN_HEX_MUSTER = re.compile(r"(?:5245|484a)(?:3[0-9]|4[1-9a-f]|5[0-9a]){14}", re.IGNORECASE)


def ersetze_klartext(zeile: str, gefunden: set[str]) -> str:
    """Seriennummern im lesbaren Teil durch X ersetzen."""

    def _ersatz(treffer: re.Match[str]) -> str:
        sn = treffer.group(1)
        gefunden.add(sn)
        # Praefix erhalten - die Geraetegeneration bleibt so erkennbar, und
        # genau die ist fuer die Fehlersuche relevant.
        return sn[:4] + "X" * (len(sn) - 4)

    return SN_MUSTER.sub(_ersatz, zeile)


def ersetze_hex(zeile: str, gefunden: set[str]) -> str:
    """Hex-kodierte Seriennummern im Frame ersetzen, Laenge beibehalten."""

    def _ersatz(treffer: re.Match[str]) -> str:
        roh = treffer.group(0)
        try:
            text = bytes.fromhex(roh).decode("ascii")
        except (ValueError, UnicodeDecodeError):
            return roh
        gefunden.add(text)
        ersatz = text[:4] + "X" * (len(text) - 4)
        # Gross-/Kleinschreibung der Hex-Ziffern beibehalten
        kodiert = ersatz.encode("ascii").hex()
        return kodiert.upper() if roh[0].isupper() else kodiert

    return SN_HEX_MUSTER.sub(_ersatz, zeile)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("datei", help="Home-Assistant-Protokoll")
    parser.add_argument(
        "--alle",
        action="store_true",
        help="alle Zeilen ausgeben, nicht nur die mit Rohframes",
    )
    args = parser.parse_args()

    gefunden: set[str] = set()
    zeilen = 0

    with open(args.datei, encoding="utf-8", errors="replace") as datei:
        for zeile in datei:
            if not args.alle and "Rohframe" not in zeile:
                continue
            zeile = ersetze_hex(zeile, gefunden)
            zeile = ersetze_klartext(zeile, gefunden)
            sys.stdout.write(zeile)
            zeilen += 1

    print(
        f"\n{zeilen} Zeilen, {len(gefunden)} Seriennummer(n) ersetzt.",
        file=sys.stderr,
    )
    if not gefunden:
        print(
            "ACHTUNG: keine Seriennummer gefunden - bitte selbst nachsehen, "
            "bevor du die Datei weitergibst.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
