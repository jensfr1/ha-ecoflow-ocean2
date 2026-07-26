<img src="icon.png" alt="" width="96" align="right">

# EcoFlow Ocean 2 für Home Assistant

[English](README.md) · **Deutsch**

Livedaten deines EcoFlow Ocean 2 in Home Assistant — PV, Batterie, Netz, Phasen
und Batteriemodule, alle ~10 Sekunden aktualisiert.

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

1. HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories*
2. URL dieses Repos eintragen, Kategorie *Integration*
3. „EcoFlow Ocean 2" installieren, Home Assistant neu starten

### Manuell

Ordner `custom_components/ecoflow_ocean2` nach `config/custom_components/`
kopieren und Home Assistant neu starten.

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

## Zwei berechnete Werte

Nicht alles kommt direkt vom Gerät:

- **Hausverbrauch** wird als `PV − Batterie + Netz` berechnet. Genauso rechnet
  auch das EcoFlow-Webportal.
- **Gesamtleistung aller Phasen** ist die Summe der Einzelphasen. Sie bleibt
  leer, solange eine Phase ihren Wert noch nicht gemeldet hat — eine Teilsumme
  wäre zu niedrig und damit irreführend.

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

[**PayPal**](https://www.paypal.com/donate/?business=jensfr%40gmail.com&currency_code=EUR)

Ein Stern auf GitHub kostet nichts und hilft genauso.

## Lizenz

MIT
