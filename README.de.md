<img src="icon.png" alt="" width="96" align="right">

# EcoFlow Ocean 2 für Home Assistant

[English](README.md) · **Deutsch**

[![Release](https://img.shields.io/github/v/release/jensfr1/ha-ecoflow-ocean2?style=for-the-badge&color=41BDF5)](https://github.com/jensfr1/ha-ecoflow-ocean2/releases)
[![Validate](https://img.shields.io/github/actions/workflow/status/jensfr1/ha-ecoflow-ocean2/validate.yml?style=for-the-badge&label=Validate)](https://github.com/jensfr1/ha-ecoflow-ocean2/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://hacs.xyz)
[![Issues](https://img.shields.io/github/issues/jensfr1/ha-ecoflow-ocean2?style=for-the-badge)](https://github.com/jensfr1/ha-ecoflow-ocean2/issues)
[![Letzter Commit](https://img.shields.io/github/last-commit/jensfr1/ha-ecoflow-ocean2?style=for-the-badge)](https://github.com/jensfr1/ha-ecoflow-ocean2/commits/main)
[![Lizenz](https://img.shields.io/github/license/jensfr1/ha-ecoflow-ocean2?style=for-the-badge)](LICENSE)

Livedaten deines EcoFlow Ocean 2 in Home Assistant — PV, Batterie, Netz, Phasen
und Batteriemodule, alle ~10 Sekunden aktualisiert.

[![Zu HACS hinzufügen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jensfr1&repository=ha-ecoflow-ocean2&category=integration)

## Warum noch eine Integration?

Für das **EcoFlow Ocean 2** (Seriennummern beginnend mit `RE11`) liefert bislang
**keine** verfügbare Lösung Daten:

| Weg | Problem |
|---|---|
| Offizielle Developer-API | Fehler `1006` — „current device is not allowed to get device info" |
| Offizielles MQTT-Topic | Verbindung klappt, es kommen aber nie Daten |
| App-REST-API (`provider-service/user/device/detail`) | Antwortet mit `code 0`, aber **leerem** Datenteil |
| Modbus TCP | Nur nach Freischaltung durch den Installateur |

Der einzige funktionierende Weg ist das **App-MQTT** von EcoFlow. Dort sendet
das Gerät Protobuf-Telemetrie — die neue Generation allerdings in der
Nachrichtenklasse **`cmdFunc 254`** (`cmdId 39` = Telemetrie, `cmdId 46` =
Batteriemodul), die bislang nirgends dokumentiert war. Die Feldzuordnung wurde
aus mitgeschnittenem Verkehr rekonstruiert und gegen das EcoFlow-Webportal
verifiziert (Abweichung ~1 %).

> **Hinweis:** Diese Integration nutzt eine inoffizielle API. EcoFlow kann sie
> jederzeit ändern.

## Installation

### HACS (empfohlen)

[![Zu HACS hinzufügen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jensfr1&repository=ha-ecoflow-ocean2&category=integration)

Ein Klick auf den Knopf öffnet das Repository direkt in deinem eigenen Home
Assistant — ohne URL-Kopieren. Dann *Herunterladen*, und Home Assistant neu
starten.

Von Hand, falls der Knopf nicht funktioniert (er setzt eingerichtetes My Home
Assistant voraus):

1. HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories*
2. URL dieses Repos eintragen, Kategorie *Integration*
3. „EcoFlow Ocean 2" installieren, Home Assistant neu starten

### Manuell

Ordner `custom_components/ecoflow_ocean2` nach `config/custom_components/`
kopieren und Home Assistant neu starten.

Vorausgesetzt wird Home Assistant 2024.10 oder neuer. Ab 2026.3 bringt die
Integration ihr Logo selbst mit (`brand/icon.png`); ältere Versionen zeigen
stattdessen das allgemeine Symbol.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → EcoFlow Ocean 2*

| Feld | |
|---|---|
| E-Mail | dein EcoFlow-Konto (wie in der App) |
| Passwort | wird beim Einrichten sofort geprüft |
| Seriennummer | die des Wechselrichters, z. B. `RE11XXXXXXXXXXXX` |

Die Zugangsdaten werden bereits im Dialog getestet — ein Tippfehler fällt also
sofort auf. Lehnt EcoFlow das Passwort später ab, fragt Home Assistant es
automatisch neu ab (Reauth).

## Entitäten

**Leistung:** Solarleistung, Batterieleistung (+ laden / − entladen),
Netzleistung (+ Bezug / − Einspeisung), Hausverbrauch, Wechselrichter-Ausgang,
Gesamtleistung aller Phasen, Leistung je PV-String.

**Batterie:** Ladestand, verbleibende Energie, „lädt"-Status; je Modul
Ladestand, Temperatur und Spannung (als eigenes Untergerät).

**Phasen:** Spannung, Strom und Wirkleistung je Phase — standardmäßig
deaktiviert, um die Geräteseite übersichtlich zu halten. Bei Bedarf in den
Entitätseinstellungen aktivieren.

**Energie (für das Energie-Dashboard):** Netzbezug, Netzeinspeisung,
Solarerzeugung, Batterie geladen/entladen, Hausverbrauch — als kWh-Zähler.

### Energie-Dashboard einrichten

Das Gerät liefert nur Momentanleistung, deshalb bildet die Integration die
kWh-Zähler selbst (Integration über die Zeit). Sie überstehen Neustarts und
rechnen Verbindungslücken **nicht** hoch — es wird also keine Energie erfunden,
die während eines Ausfalls „vielleicht" geflossen ist.

Unter *Einstellungen → Dashboards → Energie* eintragen:

| Feld im Dashboard | Entität |
|---|---|
| Netzbezug | *Grid consumption* / *Netzbezug* |
| Rückspeisung ins Netz | *Grid return* / *Netzeinspeisung* |
| Solarproduktion | *Solar production* / *Solarerzeugung* |
| Batterie: Energie hinein | *Battery charged* / *Batterie geladen* |
| Batterie: Energie heraus | *Battery discharged* / *Batterie entladen* |

*Hausverbrauch* trägst du dort **nicht** ein — den errechnet das Dashboard aus
den fünf Werten oben, sonst zählst du doppelt.

Ob die Namen deutsch oder englisch erscheinen, hängt an *Einstellungen → System
→ Allgemein → Sprache*: Entitätsnamen werden serverseitig über die
**Systemsprache** übersetzt, nicht über die Sprache deines Benutzerprofils. Die
Entity-IDs entstehen einmalig beim Einrichten und ändern sich später nicht mehr,
auch wenn du die Sprache umstellst.

## Beispiel-Automatisierungen

Diese Dinge stecken bewusst **nicht** in der Integration. Es sind persönliche
Entscheidungen — Schwellwerte, Formulierungen, welcher Messenger — und einmal
in Code gegossen lassen sie sich schlecht anpassen. Als YAML gehören sie dir.

Alle Beispiele nutzen die Entitäts-IDs `sensor.powerocean_*`. Deine können
abweichen, je nachdem wie du das Gerät benannt hast; nachschlagen unter
*Einstellungen → Geräte & Dienste → Entitäten*.

### Tageszähler als Grundlage

Mehrere Beispiele brauchen Werte „von heute". Die leitet Home Assistant nicht
von allein aus den kWh-Zählern ab — dafür gibt es `utility_meter` mit
Tageszyklus. In die `configuration.yaml`:

```yaml
utility_meter:
  ocean2_solar_taeglich:
    source: sensor.powerocean_solarerzeugung
    cycle: daily
  ocean2_netzbezug_taeglich:
    source: sensor.powerocean_netzbezug
    cycle: daily
  ocean2_einspeisung_taeglich:
    source: sensor.powerocean_netzeinspeisung
    cycle: daily
  ocean2_haus_taeglich:
    source: sensor.powerocean_hausverbrauch_energie
    cycle: daily
```

### Wie lange reicht die Batterie noch?

Restenergie geteilt durch aktuellen Verbrauch. Die `availability`-Zeile ist der
wichtige Teil: Ohne sie teilt der Sensor nachts durch null und meldet
Laufzeiten von mehreren Tagen.

```yaml
template:
  - sensor:
      - name: "Ocean 2 Restlaufzeit"
        unique_id: ocean2_restlaufzeit
        unit_of_measurement: h
        device_class: duration
        state_class: measurement
        availability: >
          {{ has_value('sensor.powerocean_verbleibende_akku_energie')
             and has_value('sensor.powerocean_hausverbrauch')
             and states('sensor.powerocean_hausverbrauch') | float(0) > 50 }}
        state: >
          {{ (states('sensor.powerocean_verbleibende_akku_energie') | float
              / states('sensor.powerocean_hausverbrauch') | float) | round(1) }}
```

### Autarkie heute

```yaml
template:
  - sensor:
      - name: "Ocean 2 Autarkie heute"
        unique_id: ocean2_autarkie_heute
        unit_of_measurement: "%"
        state_class: measurement
        availability: >
          {{ has_value('sensor.ocean2_haus_taeglich')
             and states('sensor.ocean2_haus_taeglich') | float(0) > 0.1 }}
        state: >
          {% set haus = states('sensor.ocean2_haus_taeglich') | float %}
          {% set netz = states('sensor.ocean2_netzbezug_taeglich') | float(0) %}
          {{ (100 * (haus - netz) / haus) | round(1) }}
```

### Bericht bei Sonnenuntergang

```yaml
automation:
  - alias: "Ocean 2 Tagesbericht bei Sonnenuntergang"
    trigger:
      - trigger: sun
        event: sunset
    action:
      - action: notify.persistent_notification
        data:
          title: "Solarbilanz heute"
          message: >
            Erzeugt: {{ states('sensor.ocean2_solar_taeglich') | float(0) | round(1) }} kWh
            · Haus: {{ states('sensor.ocean2_haus_taeglich') | float(0) | round(1) }} kWh
            · Aus dem Netz: {{ states('sensor.ocean2_netzbezug_taeglich') | float(0) | round(1) }} kWh
            · Eingespeist: {{ states('sensor.ocean2_einspeisung_taeglich') | float(0) | round(1) }} kWh
            · Batterie jetzt: {{ states('sensor.powerocean_batterie') }} %
```

Statt `notify.persistent_notification` den eigenen Dienst eintragen, um den
Bericht aufs Handy zu bekommen — etwa `notify.mobile_app_<dein_geraet>`.

### Warnung bei niedrigem Ladestand

```yaml
automation:
  - alias: "Ocean 2 Batterie niedrig"
    trigger:
      - trigger: numeric_state
        entity_id: sensor.powerocean_batterie
        below: 15
        for: "00:10:00"
    action:
      - action: notify.persistent_notification
        data:
          title: "Batterie niedrig"
          message: >
            Nur noch {{ states('sensor.powerocean_batterie') }} %,
            das Haus zieht {{ states('sensor.powerocean_hausverbrauch') }} W.
```

Das `for:` macht die Automatisierung erst brauchbar: Ohne die zehn Minuten löst
schon ein kurzes Unterschreiten aus, und die Meldung kommt im Minutentakt
wieder.

### Verbindungsverlust

```yaml
automation:
  - alias: "Ocean 2 Verbindung verloren"
    trigger:
      - trigger: state
        entity_id: binary_sensor.powerocean_cloud_verbindung
        to: "off"
        for: "00:15:00"
    action:
      - action: notify.persistent_notification
        data:
          title: "Ocean 2 nicht erreichbar"
          message: "Seit 15 Minuten keine Daten."
```

**Zur Stromausfall-Erkennung:** Mit den verfügbaren Daten geht das nicht
verlässlich. Naheliegend wäre, auf „Netz 0 W" zu schließen — das ist an einem
sonnigen Tag aber der Normalzustand. Ob das Netz überhaupt anliegt, meldet das
Gerät nicht. Bei einem echten Stromausfall bricht auch seine Cloud-Verbindung
ab, die Automatisierung oben löst also aus — nur eben genauso, wenn bloß dein
Internet weg ist. Die Meldung heißt „kein Kontakt", nicht „Stromausfall".

## Woher die Werte kommen

- **Hausverbrauch** kommt vom Gerät, das ihn im selben Moment mit Solar,
  Batterie und Netz bilanziert meldet. Nur wenn dieses Feld fehlt, greift eine
  Rechnung — und die fällt systematisch zu niedrig aus, weil die Felder, auf
  die sie sich stützt, unabhängig voneinander aktualisiert werden und damit aus
  verschiedenen Momenten stammen.
- **Gesamtleistung aller Phasen** ist die Summe der Einzelphasen. Sie bleibt
  leer, solange eine Phase ihren Wert noch nicht gemeldet hat — eine Teilsumme
  wäre zu niedrig und damit irreführend.

> **Was der Hausverbrauch wirklich bedeutet:** Das Gerät meldet, was dein Haus
> *zusätzlich* zu allem braucht, was hinter seinem Messpunkt einspeist. Läuft
> bei dir eine zweite, nicht mitgemessene Quelle — etwa ein Balkonkraftwerk —,
> taucht deren Ertrag nie auf, und der angezeigte Hausverbrauch liegt unter dem
> tatsächlichen.

## Stabilität

- **Push statt Polling:** Die MQTT-Verbindung bleibt offen, Werte kommen von
  selbst. Ein Weckruf alle 60 Sekunden hält den Datenstrom am Leben — ohne ihn
  verstummt das Gerät, sobald keine EcoFlow-App offen ist.
- **Reconnect mit erneuter Anmeldung:** Bleiben Daten aus, holt die Integration
  Token und MQTT-Zertifikat neu, statt endlos mit abgelaufenen Zugangsdaten zu
  verbinden.
- **Ehrliche Verfügbarkeit:** Reißt der Datenstrom ab, werden die Messwerte als
  *nicht verfügbar* markiert, statt alte Werte als aktuell auszugeben. Die
  Energiezähler bleiben davon unberührt.
- **Gedrosselte Updates:** Das Gerät sendet alle ~2 Sekunden; geschrieben wird
  höchstens alle 10 Sekunden. Das entlastet Datenbank und SD-Karte spürbar.

## Ein Wert sieht falsch aus?

Dann liegt es fast sicher an der Feldzuordnung, nicht an Home Assistant — diese
Generation sendet in einer undokumentierten Nachrichtenklasse, und ein Feld
kann an deiner Anlage etwas anderes bedeuten als an meiner. So kam der bisher
gröbste Fehler ans Licht: Was wie der Netzzähler aussah, war in Wahrheit die
Einspeisebegrenzung eines Nutzers.

**[→ Werte prüfen und Rohdaten liefern](DEBUGGING.de.md)**

Die Anleitung erklärt Diagnosedaten, Debug-Protokollierung, was du parallel aus
der App notieren solltest, und ein Skript, das deine Seriennummer aus dem
Mitschnitt entfernt, bevor du ihn weitergibst.

## Entwicklung

```bash
pip install pytest
python -m pytest tests/ -q
```

Die Fachlogik (Decoder, Merge, Energie-Integration) ist bewusst frei von
Home-Assistant-Importen und damit ohne HA testbar. Die Tests laufen gegen
**echte, aufgezeichnete Payloads** der Anlage.

Zusätzlich prüft `tests/crosscheck_ts.py`, ob der Python-Decoder exakt dieselben
Werte liefert wie die TypeScript-Referenzimplementierung.

## Dank

Die Reverse-Engineering-Vorarbeit anderer Projekte hat geholfen, das
Rahmenformat zu verstehen — insbesondere
[foxthefox/ioBroker.ecoflow-mqtt](https://github.com/foxthefox/ioBroker.ecoflow-mqtt)
und [Feberdin/ecoflow-powerocean-ha](https://github.com/Feberdin/ecoflow-powerocean-ha)
(beide MIT). Die Dekodierung von `cmdFunc 254` ist eigene Arbeit.

## Unterstützung

Ich baue das in meiner Freizeit und gebe es her. Wenn es dir etwas spart und du
es erübrigen kannst, freue ich mich über einen kleinen Beitrag — erwartet wird
nichts, und nichts ist davon abhängig.

<a href="https://buymeacoffee.com/jensfr"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00?style=flat&logo=buymeacoffee&logoColor=black" alt="Buy me a coffee"></a>

Ein Stern auf GitHub kostet nichts und hilft genauso.

## Lizenz

MIT
