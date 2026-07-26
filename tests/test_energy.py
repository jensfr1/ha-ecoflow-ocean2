"""Tests der Energie-Integration.

Der kritische Punkt sind Luecken: Nach einem Verbindungsabbruch darf die
letzte bekannte Leistung nicht ueber die ganze Ausfallzeit hochgerechnet
werden - das wuerde Energie erfinden.
"""

from __future__ import annotations

import pytest

from custom_components.ecoflow_ocean2.energy import (
    MAX_GAP,
    EnergyIntegrator,
    negative,
    positive,
)


class TestIntegration:
    def test_konstante_leistung(self) -> None:
        # 1000 W ueber 60 s = 16,67 Wh. Realistischer Takt: Der Coordinator
        # liefert etwa alle 10 s, Intervalle liegen also weit unter MAX_GAP.
        integrator = EnergyIntegrator()
        integrator.add(1000.0, 0.0)
        total = integrator.add(1000.0, 60.0)
        assert total == pytest.approx(1000.0 * 60 / 3600)

    def test_eine_stunde_in_realistischen_schritten(self) -> None:
        integrator = EnergyIntegrator()
        for step in range(0, 3601, 60):  # 60 Intervalle a 60 s
            integrator.add(1000.0, float(step))
        assert integrator.total_wh == pytest.approx(1000.0)  # 1000 W * 1 h

    def test_erster_wert_zaehlt_nichts(self) -> None:
        # Ohne Vorwert gibt es kein Intervall
        integrator = EnergyIntegrator()
        assert integrator.add(5000.0, 0.0) == 0.0

    def test_trapezregel_bei_steigender_leistung(self) -> None:
        integrator = EnergyIntegrator()
        integrator.add(0.0, 0.0)
        total = integrator.add(2000.0, 60.0)
        # Mittel aus 0 und 2000 = 1000 W ueber 60 s
        assert total == pytest.approx(1000.0 * 60 / 3600)

    def test_summiert_ueber_mehrere_intervalle(self) -> None:
        integrator = EnergyIntegrator()
        for step in range(4):
            integrator.add(3600.0, step * 1.0)  # 3600 W, 1-Sekunden-Takt
        # 3 Intervalle a 1 s bei 3600 W = 3 Wh
        assert integrator.total_wh == pytest.approx(3.0)

    def test_none_wird_ignoriert(self) -> None:
        integrator = EnergyIntegrator()
        integrator.add(1000.0, 0.0)
        assert integrator.add(None, 3600.0) == 0.0


class TestLuecken:
    def test_grosse_luecke_wird_nicht_angerechnet(self) -> None:
        integrator = EnergyIntegrator()
        integrator.add(1000.0, 0.0)
        # Eine Stunde Verbindungsabbruch
        total = integrator.add(1000.0, MAX_GAP + 1)
        assert total == 0.0

    def test_nach_luecke_wird_normal_weitergezaehlt(self) -> None:
        integrator = EnergyIntegrator()
        integrator.add(1000.0, 0.0)
        integrator.add(1000.0, MAX_GAP + 1)  # Luecke - verworfen
        total = integrator.add(1000.0, MAX_GAP + 61)
        assert total == pytest.approx(1000.0 * 60 / 3600)

    def test_zeitruecksprung_wird_ignoriert(self) -> None:
        integrator = EnergyIntegrator()
        integrator.add(1000.0, 100.0)
        assert integrator.add(1000.0, 50.0) == 0.0


class TestNeustart:
    def test_stellt_zaehlerstand_wieder_her(self) -> None:
        integrator = EnergyIntegrator()
        integrator.restore(4321.5)
        assert integrator.total_wh == 4321.5

    def test_fuellt_die_neustart_luecke_nicht(self) -> None:
        # Nach restore() fehlt der Zeitbezug bewusst - der erste Wert nach dem
        # Neustart darf keine Energie fuer die Ausfallzeit erzeugen.
        integrator = EnergyIntegrator()
        integrator.restore(1000.0)
        assert integrator.add(5000.0, 99999.0) == 1000.0
        # ab dem zweiten Wert wird wieder normal gezaehlt
        assert integrator.add(5000.0, 99999.0 + 60) == pytest.approx(
            1000.0 + 5000.0 * 60 / 3600
        )


class TestVorzeichen:
    @pytest.mark.parametrize(
        ("value", "expected_positive", "expected_negative"),
        [(500.0, 500.0, 0.0), (-500.0, 0.0, 500.0), (0.0, 0.0, 0.0)],
    )
    def test_trennt_bezug_und_einspeisung(
        self, value: float, expected_positive: float, expected_negative: float
    ) -> None:
        assert positive(value) == expected_positive
        assert negative(value) == expected_negative

    def test_none_bleibt_none(self) -> None:
        assert positive(None) is None
        assert negative(None) is None
