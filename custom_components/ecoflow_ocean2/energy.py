"""Energiezaehler aus Leistungswerten.

Das Geraet meldet nur Momentanleistung, das Energie-Dashboard braucht aber
kWh-Zaehler. Diese werden hier durch Integration ueber die Zeit gebildet
(Trapezregel).

Zwei Dinge sind dabei wichtig:

* **Luecken nicht mitintegrieren.** War die Verbindung eine Stunde weg, darf
  die letzte bekannte Leistung nicht ueber diese Stunde hochgerechnet werden -
  das erfindet Energie. Ab ``MAX_GAP`` wird das Intervall verworfen.
* **Neustartfest.** Der Zaehlerstand wird ueber ``RestoreEntity`` wieder
  hergestellt, sonst faellt er auf 0 und das Dashboard sieht einen Reset.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Laengere Pausen werden nicht integriert (Verbindungsabbruch, HA-Neustart).
MAX_GAP = 300.0


@dataclass
class EnergyIntegrator:
    """Integriert eine Leistung (W) zu Energie (Wh)."""

    total_wh: float = 0.0
    _last_time: float | None = None
    _last_power: float | None = None

    def restore(self, total_wh: float) -> None:
        """Setzt einen wiederhergestellten Zaehlerstand.

        Der Zeitbezug wird bewusst nicht wiederhergestellt: Die Zeit seit dem
        letzten Wert vor dem Neustart ist eine Luecke und wird nicht gefuellt.
        """
        self.total_wh = total_wh
        self._last_time = None
        self._last_power = None

    def add(self, power_w: float | None, now: float) -> float:
        """Verarbeitet einen Messwert und gibt den Zaehlerstand in Wh zurueck."""
        if power_w is None:
            return self.total_wh

        previous_time = self._last_time
        previous_power = self._last_power
        self._last_time = now
        self._last_power = power_w

        if previous_time is None or previous_power is None:
            return self.total_wh

        elapsed = now - previous_time
        if elapsed <= 0 or elapsed > MAX_GAP:
            # Ruecksprung der Uhr oder zu grosse Luecke - nichts anrechnen
            return self.total_wh

        # Trapezregel: Mittelwert beider Leistungen ueber das Intervall
        self.total_wh += (previous_power + power_w) / 2 * (elapsed / 3600)
        return self.total_wh


def positive(value: float | None) -> float | None:
    """Nur der positive Anteil (z.B. Netzbezug aus der signierten Netzleistung)."""
    if value is None:
        return None
    return max(0.0, value)


def negative(value: float | None) -> float | None:
    """Nur der negative Anteil als positive Zahl (z.B. Einspeisung)."""
    if value is None:
        return None
    return max(0.0, -value)
