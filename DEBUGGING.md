<img src="icon.png" alt="" width="96" align="right">

# Checking values and providing data for troubleshooting

**English** · [Deutsch](DEBUGGING.de.md)

When a value does not match what the EcoFlow app shows, the cause is almost
never Home Assistant — it is the mapping of the protocol fields. This
generation of the Ocean 2 sends in a message class EcoFlow never documented;
every field in it was worked out from captured traffic. A field can therefore
mean something different on your system than on mine.

That is exactly how the worst bug so far came to light: a user reported a
constant grid power of 10 kW. In his raw data, the supposed grid field read
`10000` at all times — it was not a measurement but his export limit. On my
system, which exports nothing, that field always read 0, which is why the error
could have gone unnoticed for years.

So I need two things from you: **the raw data** and **the values your app shows
at the same moment**. Without that comparison the raw data is just numbers.

## The quick route: diagnostics

Often enough when a single value looks wrong.

*Settings → Devices & Services → EcoFlow Ocean 2 → ⋮ → **Download diagnostics***

The file contains the current state of every value. Credentials and the serial
number are already stripped — you can attach it to an issue as it is.

## The thorough route: capturing raw frames

Needed when the mapping itself is wrong — then I have to see the bytes.

### 1. Turn on debug logging

Easiest through the interface:

*Settings → Devices & Services → EcoFlow Ocean 2 → ⋮ → **Enable debug logging***

Or permanently via `configuration.yaml` (needs a restart):

```yaml
logger:
  default: warning
  logs:
    custom_components.ecoflow_ocean2: debug
```

### 2. Let it run for a few minutes

Five minutes are enough. It becomes useful when something changes during that
time — the battery switching direction, a cloud passing, a large appliance
starting. A capture taken while nothing moves says little.

**Note down from the EcoFlow app**, with the time:

```
Time:     18:09
Solar:    3600 W
House:     560 W
Grid:        0 W    (minus = export, plus = import)
Battery:  3040 W    (charging)
```

The sign of the grid value matters — write down whether you were exporting or
importing. That detail nearly caused a misdiagnosis last time.

### 3. Get the log

*Settings → System → Logs → **Load full logs***

Or the file `config/home-assistant.log` directly.

The relevant lines look like this:

```
2026-07-28 18:09:17.468 DEBUG (...) [custom_components.ecoflow_ocean2.client]
MQTT-Rohframe (196 Bytes): 0ac1010a683a0a0d008009442500a03e45...
```

### 4. Remove the serial number

**Your serial number sits in plain sight in every frame** — as readable
characters and additionally hex-encoded. It is not a password, but it still
does not belong in a public issue.

The repository contains a small script that replaces both while preserving the
length (otherwise the frames would be unusable):

```bash
python scripts/anonymize_log.py home-assistant.log > capture.txt
```

It finds serial numbers on its own, you do not have to pass anything. At the
end it reports how many it replaced — if that says 0, please check before
handing the file on.

### 5. Turn debug logging off again

Do not forget: at `debug` the integration records every message it receives,
around 30 lines per minute. Over days that fills the disk, and on a Raspberry
Pi the SD card.

## Where to send it

As an [issue](https://github.com/jensfr1/ha-ecoflow-ocean2/issues) with the
capture attached and the app values in the text. Also useful:

- **How many battery modules**, and single- or three-phase
- **Export limit**, if you have one (0 kW, 10 kW, 70 %)
- **Other generators** that do not run through the Ocean — a balcony solar
  unit, for instance, appears in no measurement and makes house consumption
  look too low

That last point sounds like a detail but has already cost an hour of searching
in the wrong place.
