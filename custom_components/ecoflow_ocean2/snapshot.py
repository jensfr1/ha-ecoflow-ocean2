"""Zusammenfuehren der dekodierten MQTT-Nachrichten zu einem Gesamtbild.

Das Geraet sendet keine vollstaendigen Zustaende, sondern Bruchstuecke in
mehreren Nachrichtentypen. Phasen und PV-Strings kommen zusaetzlich
delta-kodiert - also nur die Felder, die sich geaendert haben.

Daraus folgt die wichtigste Regel dieses Moduls: **Ein fehlendes Feld darf
den Vorwert nicht ueberschreiben.** Nie empfangene Werte bleiben ``None`` und
werden von der Integration gar nicht erst als Sensorwert veroeffentlicht -
eine 0 waere eine erfundene Messung.

Bewusst ohne Home-Assistant-Importe, damit die Logik isoliert testbar bleibt.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .protobuf import DecodedMessage, Phase

PHASE_KEYS = ("a", "b", "c")


@dataclass
class PhaseValues:
    """Messwerte einer Phase. ``None`` = noch nie uebertragen."""

    voltage: float | None = None
    current: float | None = None
    active_power: float | None = None
    reactive_power: float | None = None
    apparent_power: float | None = None


@dataclass
class BatteryModule:
    """Zustand eines Batterie-Moduls."""

    index: int
    sn: str
    soc: float
    temperature: float
    voltage: float
    capacity_wh: float
    #: Modul-Leistung in W: positiv = laden, negativ = entladen
    power_w: float | None = None
    #: Alterungszustand in %
    soh_percent: float | None = None
    #: Bisherige Vollzyklen
    cycles: int | None = None


@dataclass
class Snapshot:
    """Gesamtzustand der Anlage.

    Vorzeichen:
        battery_power_w  positiv = laden,  negativ = entladen
        grid_power_w     positiv = Bezug,  negativ = Einspeisung
    """

    sn: str
    updated_at: float = 0.0
    pv_power_w: float | None = None
    battery_power_w: float | None = None
    battery_soc: float | None = None
    battery_remaining_wh: float | None = None
    grid_power_w: float | None = None
    inverter_power_w: float | None = None
    #: Vom Geraet gemeldet, sonst berechnet - siehe compute_house_load()
    house_power_w: float | None = None
    #: True, sobald die Hauslast einmal gemessen kam (dann nie mehr rechnen)
    house_power_measured: bool = False
    phases: dict[str, PhaseValues] = field(default_factory=dict)
    #: String-Index -> Leistung in W
    pv_strings: dict[int, float] = field(default_factory=dict)
    #: Modul-Index -> Zustand
    battery_modules: dict[int, BatteryModule] = field(default_factory=dict)


def empty_snapshot(sn: str) -> Snapshot:
    """Leerer Ausgangszustand."""
    return Snapshot(sn=sn)


def _merge_phase(previous: PhaseValues | None, partial: dict[str, float]) -> PhaseValues:
    """Uebernimmt nur die tatsaechlich uebertragenen Felder (Delta-Kodierung)."""
    base = previous or PhaseValues()
    return PhaseValues(
        voltage=partial.get("vol", base.voltage),
        current=partial.get("amp", base.current),
        active_power=partial.get("act_pwr", base.active_power),
        reactive_power=partial.get("react_pwr", base.reactive_power),
        apparent_power=partial.get("apparent_pwr", base.apparent_power),
    )


def _full_phase(phase: Phase) -> PhaseValues:
    """Vollstaendige Phase der aelteren Generation uebernehmen."""
    return PhaseValues(
        voltage=phase.vol,
        current=phase.amp,
        active_power=phase.act_pwr,
        reactive_power=phase.react_pwr,
        apparent_power=phase.apparent_pwr,
    )


#: Totzone um null, wie sie EcoFlow selbst anwendet.
#:
#: Der Zaehler misst auch im Leerlauf ein paar Watt in die eine oder andere
#: Richtung. Im Portal und in der App taucht das nie auf: Deren Verlaufsexport
#: enthaelt ausschliesslich 0 oder Betraege ab 30 W. Ohne diese Schwelle zeigt
#: Home Assistant "7 W Bezug", waehrend die App daneben 0 W meldet - und jemand
#: sucht den Fehler bei sich.
GRID_DEADBAND_W = 30.0


def apply_grid_deadband(watt: float) -> float:
    """Kleine Messwerte um null auf 0 ziehen."""
    return 0.0 if abs(watt) < GRID_DEADBAND_W else watt


def compute_house_load(snapshot: Snapshot) -> float | None:
    """Hauslast aus den beiden Quellen am Hausknoten.

    Das Geraet meldet die Hauslast nicht direkt. Am Hausknoten haengen aber
    genau zwei Quellen: der Wechselrichter (der PV und Batterie bereits
    verrechnet hat) und das Netz.

        Last = Wechselrichter-Ausgang + Netzbezug

    Das ist genauer als der Umweg ueber ``PV - Batterie + Netz``, weil die
    Wandlungsverluste schon im Wechselrichterwert stecken. Gegengeprueft am
    27.07.2026: 183 + (-2) = 181 W, das Geraet meldete im selben Moment 171 W.
    Beim Laden aus dem Netz: -1530 + 1719 = 189 W.

    Fehlt einer der beiden Werte, greift die alte Bilanz als Rueckfallebene.
    """
    if snapshot.inverter_power_w is not None and snapshot.grid_power_w is not None:
        return max(0.0, snapshot.inverter_power_w + snapshot.grid_power_w)
    if snapshot.pv_power_w is None:
        return None
    return max(
        0.0,
        snapshot.pv_power_w
        - (snapshot.battery_power_w or 0.0)
        + (snapshot.grid_power_w or 0.0),
    )


def sum_phases(snapshot: Snapshot, attribute: str) -> float | None:
    """Summe eines Phasenwerts ueber alle vorhandenen Phasen.

    Liefert ``None``, sobald eine vorhandene Phase den Wert noch nicht gemeldet
    hat - eine Teilsumme waere zu niedrig und damit irrefuehrend. Phasen, die es
    am System gar nicht gibt, werden uebersprungen (einphasige Anlagen).
    """
    present = [p for key in PHASE_KEYS if (p := snapshot.phases.get(key)) is not None]
    if not present:
        return None
    total = 0.0
    for phase in present:
        value = getattr(phase, attribute)
        if value is None:
            return None
        total += value
    return total


def average_phases(snapshot: Snapshot, attribute: str) -> float | None:
    """Mittelwert - sinnvoll fuer die Spannung, wo Summieren unsinnig waere."""
    present = [p for key in PHASE_KEYS if (p := snapshot.phases.get(key)) is not None]
    values = [v for p in present if (v := getattr(p, attribute)) is not None]
    if not values or len(values) != len(present):
        return None
    return sum(values) / len(values)


def merge_snapshot(
    sn: str, previous: Snapshot | None, message: DecodedMessage, now: float
) -> Snapshot:
    """Fuehrt eine dekodierte Nachricht in den Vorzustand ein.

    ``previous`` wird nicht veraendert; es kommt immer ein neues Objekt zurueck.
    """
    base = previous or empty_snapshot(sn)
    snapshot = replace(
        base,
        sn=sn,
        updated_at=now,
        phases=dict(base.phases),
        pv_strings=dict(base.pv_strings),
        battery_modules=dict(base.battery_modules),
    )

    # Sobald das Geraet die Hauslast einmal selbst gemeldet hat, wird sie nie
    # wieder gerechnet. Sonst wuerde jede Nachricht ohne dieses Feld den guten
    # Wert durch den zu niedrigen ersetzen, und die Anzeige springt im
    # Sekundentakt hin und her.
    hauslast_gemessen = base.house_power_measured

    # ── Aeltere Generation (cmdFunc 96) ──────────────────────────────────────
    if stream := message.energy_stream:
        snapshot.battery_soc = stream.bp_soc
        snapshot.battery_power_w = stream.bp_pwr
        snapshot.pv_power_w = stream.mppt_pwr
        snapshot.grid_power_w = stream.sys_grid_pwr
        snapshot.house_power_w = stream.sys_load_pwr  # hier echter Messwert
        hauslast_gemessen = True

    if heartbeat := message.ems_heartbeat:
        snapshot.phases = {
            "a": _full_phase(heartbeat.pcs_a_phase),
            "b": _full_phase(heartbeat.pcs_b_phase),
            "c": _full_phase(heartbeat.pcs_c_phase),
        }
        for index, pv in enumerate(heartbeat.pv_strings, start=1):
            snapshot.pv_strings[index] = pv.pwr
        if snapshot.battery_power_w is None and heartbeat.ems_bp_power != 0:
            snapshot.battery_power_w = heartbeat.ems_bp_power
        if heartbeat.bp_remain_wh > 0:
            snapshot.battery_remaining_wh = heartbeat.bp_remain_wh

    for pack in message.battery_packs:
        snapshot.battery_modules[pack.pack_index] = BatteryModule(
            index=pack.pack_index,
            sn=pack.sn,
            soc=pack.real_soc or pack.soc,
            temperature=pack.temp_env,
            voltage=pack.vol,
            capacity_wh=pack.remain_wh,
            power_w=pack.pwr,
            soh_percent=pack.soh,
            cycles=int(pack.cycles),
        )

    # ── Neue Generation (cmdFunc 254) ────────────────────────────────────────
    if telemetry := message.po2_telemetry:
        if telemetry.pv_power_w is not None:
            snapshot.pv_power_w = telemetry.pv_power_w
        if telemetry.grid_power_w is not None:
            snapshot.grid_power_w = apply_grid_deadband(telemetry.grid_power_w)
        if telemetry.battery_power_w is not None:
            snapshot.battery_power_w = telemetry.battery_power_w
        # SoC 0 kommt in Teilnachrichten als Platzhalter vor
        if telemetry.soc_percent:
            snapshot.battery_soc = telemetry.soc_percent
        if telemetry.remaining_wh:
            snapshot.battery_remaining_wh = telemetry.remaining_wh
        if telemetry.pcs_total_w is not None:
            snapshot.inverter_power_w = telemetry.pcs_total_w
        # Gemessen schlaegt gerechnet - siehe compute_house_load()
        if telemetry.house_power_w is not None:
            snapshot.house_power_w = max(0.0, telemetry.house_power_w)
            hauslast_gemessen = True

        for index, partial in telemetry.phases.items():
            key = PHASE_KEYS[index - 1]
            snapshot.phases[key] = _merge_phase(snapshot.phases.get(key), partial)

        snapshot.pv_strings.update(telemetry.pv_strings)

    for po2_pack in message.po2_battery_packs:
        snapshot.battery_modules[po2_pack.pack_index] = BatteryModule(
            index=po2_pack.pack_index,
            sn=po2_pack.sn,
            soc=po2_pack.real_soc or po2_pack.soc_percent,
            temperature=po2_pack.temp_c,
            voltage=po2_pack.voltage_v,
            capacity_wh=po2_pack.full_capacity_wh,
            power_w=po2_pack.power_w,
            soh_percent=po2_pack.soh_percent,
            cycles=po2_pack.cycles,
        )

    # Hauslast nur berechnen, wenn sie nicht schon gemessen vorliegt
    snapshot.house_power_measured = hauslast_gemessen
    if not hauslast_gemessen:
        snapshot.house_power_w = compute_house_load(snapshot)

    return snapshot
