<img src="icon.png" alt="" width="96" align="right">

# Werte prüfen und Daten für die Fehlersuche liefern

[English](DEBUGGING.md) · **Deutsch**

Wenn ein Wert nicht zu dem passt, was die EcoFlow-App zeigt, liegt das fast nie
an Home Assistant, sondern an der Zuordnung der Protokollfelder. Die Ocean-2-
Generation sendet in einer Nachrichtenklasse, die EcoFlow nicht dokumentiert
hat — jedes Feld darin wurde aus mitgeschnittenem Verkehr erschlossen. An einer
anderen Anlage kann ein Feld deshalb etwas anderes bedeuten als an meiner.

Genau so wurde der bisher gröbste Fehler gefunden: Ein Nutzer meldete eine
konstante Netzleistung von 10 kW. In seinen Rohdaten stand im vermeintlichen
Netzfeld dauerhaft `10000` — es war nicht die Messung, sondern seine
Einspeisebegrenzung. An meiner Anlage mit Nulleinspeisung stand dort immer 0,
weshalb der Fehler jahrelang unentdeckt geblieben wäre.

Dafür brauche ich zwei Dinge von dir: **die Rohdaten** und **die Werte, die
deine App im selben Moment zeigt**. Ohne den Vergleich sind die Rohdaten nur
Zahlen.

## Der schnelle Weg: Diagnosedaten

Reicht oft schon, wenn nur ein einzelner Wert falsch aussieht.

*Einstellungen → Geräte & Dienste → EcoFlow Ocean 2 → ⋮ → **Diagnose
herunterladen***

Die Datei enthält den aktuellen Zustand aller Werte. Zugangsdaten und
Seriennummer sind bereits entfernt — du kannst sie bedenkenlos an ein Issue
anhängen.

## Der gründliche Weg: Rohframes mitschneiden

Nötig, wenn die Zuordnung selbst falsch ist — dann muss ich die Bytes sehen.

### 1. Debug-Protokollierung einschalten

Am einfachsten über die Oberfläche:

*Einstellungen → Geräte & Dienste → EcoFlow Ocean 2 → ⋮ → **Debug-Protokollierung
aktivieren***

Alternativ dauerhaft über die `configuration.yaml` (Neustart nötig):

```yaml
logger:
  default: warning
  logs:
    custom_components.ecoflow_ocean2: debug
```

### 2. Ein paar Minuten laufen lassen

Fünf Minuten genügen. Aussagekräftig wird es, wenn sich in dieser Zeit etwas
ändert — die Batterie umschaltet, eine Wolke zieht durch, ein großer
Verbraucher springt an. Ein Mitschnitt bei völlig gleichbleibender Lage zeigt
wenig.

**Notiere dir dabei aus der EcoFlow-App** mit Uhrzeit:

```
Uhrzeit:   18:09
Solar:     3600 W
Haus:      560 W
Netz:      0 W      (Minus = Einspeisung, Plus = Bezug)
Batterie:  3040 W   (lädt)
```

Das Vorzeichen beim Netzwert ist wichtig — schreib dazu, ob eingespeist oder
bezogen wurde. Genau daran ist beim letzten Mal fast eine Fehldiagnose
entstanden.

### 3. Protokoll holen

*Einstellungen → System → Protokolle → **Vollständiges Protokoll laden***

Oder direkt die Datei `config/home-assistant.log`.

Die interessanten Zeilen sehen so aus:

```
2026-07-28 18:09:17.468 DEBUG (...) [custom_components.ecoflow_ocean2.client]
MQTT-Rohframe (196 Bytes): 0ac1010a683a0a0d008009442500a03e45...
```

### 4. Seriennummer entfernen

**Deine Seriennummer steckt im Klartext in jedem Frame** — als lesbare Zeichen
und zusätzlich hexadezimal kodiert. Sie ist kein Passwort, gehört aber trotzdem
nicht in ein öffentliches Issue.

Im Repository liegt dafür ein kleines Skript, das beides ersetzt und dabei die
Länge beibehält (sonst wären die Frames unbrauchbar):

```bash
python scripts/anonymize_log.py home-assistant.log > mitschnitt.txt
```

Es erkennt Seriennummern selbst, du musst nichts angeben. Am Ende meldet es,
wie viele es ersetzt hat — steht dort 0, prüf bitte nach, bevor du die Datei
weitergibst.

### 5. Debug wieder ausschalten

Nicht vergessen: Auf `debug` schreibt die Integration jede empfangene Nachricht
mit, also rund 30 Zeilen pro Minute. Über Tage füllt das die Festplatte und auf
einem Raspberry Pi die SD-Karte.

## Wohin damit

Als [Issue](https://github.com/jensfr1/ha-ecoflow-ocean2/issues) mit dem
Mitschnitt als Anhang und den App-Werten im Text. Nützlich sind außerdem:

- **Wie viele Batteriemodule** und ob ein- oder dreiphasig
- **Einspeisebegrenzung**, falls du eine hast (0 kW, 10 kW, 70 %)
- **Weitere Erzeuger**, die nicht über den Ocean laufen — ein Balkonkraftwerk
  etwa taucht in keinem Messwert auf und lässt den Hausverbrauch zu niedrig
  erscheinen

Der letzte Punkt klingt nebensächlich, hat aber schon einmal eine Stunde
Fehlersuche gekostet.
