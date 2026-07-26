<img src="icon.png" alt="" width="96" align="right">

# EcoFlow Ocean 2 for Home Assistant

**English** · [Deutsch](README.de.md)

Live data from your EcoFlow Ocean 2 in Home Assistant — solar, battery, grid,
phases and battery modules, refreshed every ~10 seconds.

## Why another integration?

For the **EcoFlow Ocean 2** (serial numbers starting with `RE11`), **no**
available solution returns data:

| Route | Problem |
|---|---|
| Official Developer API | Error `1006` — "current device is not allowed to get device info" |
| Official MQTT topic | Connects fine, but never delivers data |
| App REST API (`provider-service/user/device/detail`) | Answers `code 0` with an **empty** payload |
| Modbus TCP | Only after the installer unlocks it |

The one route that works is EcoFlow's **app MQTT**. The device sends protobuf
telemetry there — but this generation uses message class **`cmdFunc 254`**
(`cmdId 39` = telemetry, `cmdId 46` = battery module), which was not documented
anywhere. The field mapping was reconstructed from captured traffic and verified
against the EcoFlow web portal (deviation ~1 %).

> **Note:** This integration uses an unofficial API. EcoFlow can change it at
> any time.

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → *Custom repositories*
2. Add the URL of this repository, category *Integration*
3. Install "EcoFlow Ocean 2", restart Home Assistant

### Manual

Copy the folder `custom_components/ecoflow_ocean2` into
`config/custom_components/` and restart Home Assistant.

## Setup

*Settings → Devices & Services → Add Integration → EcoFlow Ocean 2*

| Field | |
|---|---|
| Email | your EcoFlow account (the same as in the app) |
| Password | verified immediately during setup |
| Serial number | the one of the inverter, e.g. `RE11XXXXXXXXXXXX` |

Credentials are tested right in the dialog, so a typo shows up immediately. If
EcoFlow rejects the password later on, Home Assistant asks for it again
(reauth).

## Entities

**Power:** solar power, battery power (+ charging / − discharging), grid power
(+ import / − export), house consumption, inverter output, total power across
all phases, power per PV string.

**Battery:** state of charge, remaining energy, "charging" status; per module
state of charge, temperature and voltage (as its own sub-device).

**Phases:** voltage, current and active power per phase — disabled by default to
keep the device page readable. Enable them in the entity settings if you need
them.

**Energy (for the energy dashboard):** grid consumption, grid return, solar
production, battery charged/discharged, house consumption — as kWh counters.

### Setting up the energy dashboard

The device only reports instantaneous power, so the integration builds the kWh
counters itself (integration over time). They survive restarts and do **not**
extrapolate across connection gaps — no energy is invented that "might" have
flowed during an outage.

Configure under *Settings → Dashboards → Energy*:

| Field in the dashboard | Entity |
|---|---|
| Grid consumption | *Grid consumption* |
| Return to grid | *Grid return* |
| Solar production | *Solar production* |
| Battery: energy going in | *Battery charged* |
| Battery: energy going out | *Battery discharged* |

Do **not** add *house consumption* there — the dashboard derives it from the
five values above, so adding it would count twice.

Whether the names appear in English or in your language depends on *Settings →
System → General → Language*: entity names are translated server-side using the
**system language**, not the language of your user profile. Entity IDs are
generated once during setup and do not change later, even if you switch the
language.

## Two calculated values

Not everything comes straight from the device:

- **House consumption** is calculated as `solar − battery + grid`. The EcoFlow
  web portal does the same.
- **Total power across all phases** is the sum of the individual phases. It
  stays empty as long as one phase has not reported its value yet — a partial
  sum would be too low and therefore misleading.

## Stability

- **Push instead of polling:** the MQTT connection stays open and values arrive
  on their own. A wake-up call every 60 seconds keeps the stream alive — without
  it the device goes silent as soon as no EcoFlow app is open.
- **Reconnect with re-login:** if data stops arriving, the integration fetches a
  fresh token and MQTT certificate instead of reconnecting forever with expired
  credentials.
- **Honest availability:** when the stream breaks, measurements are marked
  *unavailable* rather than presenting stale values as current. The energy
  counters are unaffected by this.
- **Throttled updates:** the device sends about every 2 seconds; states are
  written at most every 10 seconds. That noticeably relieves the database and
  the SD card.

## Development

```bash
pip install pytest
python -m pytest tests/ -q
```

The domain logic (decoder, merge, energy integration) is deliberately free of
Home Assistant imports and therefore testable without HA. The tests run against
**real, recorded payloads** from the system.

In addition, `tests/crosscheck_ts.py` verifies that the Python decoder returns
exactly the same values as the TypeScript reference implementation.

## Acknowledgements

Reverse-engineering work done by other projects helped to understand the frame
format — in particular
[foxthefox/ioBroker.ecoflow-mqtt](https://github.com/foxthefox/ioBroker.ecoflow-mqtt)
and [Feberdin/ecoflow-powerocean-ha](https://github.com/Feberdin/ecoflow-powerocean-ha)
(both MIT). Decoding `cmdFunc 254` is original work.

## License

MIT
