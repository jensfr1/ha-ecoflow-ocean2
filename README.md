<img src="icon.png" alt="" width="96" align="right">

# EcoFlow Ocean 2 for Home Assistant

**English** · [Deutsch](README.de.md)

[![Release](https://img.shields.io/github/v/release/jensfr1/ha-ecoflow-ocean2?style=for-the-badge&color=41BDF5)](https://github.com/jensfr1/ha-ecoflow-ocean2/releases)
[![Validate](https://img.shields.io/github/actions/workflow/status/jensfr1/ha-ecoflow-ocean2/validate.yml?style=for-the-badge&label=Validate)](https://github.com/jensfr1/ha-ecoflow-ocean2/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://hacs.xyz)
[![Issues](https://img.shields.io/github/issues/jensfr1/ha-ecoflow-ocean2?style=for-the-badge)](https://github.com/jensfr1/ha-ecoflow-ocean2/issues)
[![Last commit](https://img.shields.io/github/last-commit/jensfr1/ha-ecoflow-ocean2?style=for-the-badge)](https://github.com/jensfr1/ha-ecoflow-ocean2/commits/main)
[![License](https://img.shields.io/github/license/jensfr1/ha-ecoflow-ocean2?style=for-the-badge)](LICENSE)

Live data from your EcoFlow Ocean 2 in Home Assistant — solar, battery, grid,
phases and battery modules, refreshed every ~10 seconds.

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jensfr1&repository=ha-ecoflow-ocean2&category=integration)

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

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jensfr1&repository=ha-ecoflow-ocean2&category=integration)

One click on the button opens the repository directly in your own Home
Assistant — no copying of URLs. Then *Download*, and restart Home Assistant.

Manually, if the button does not work (it needs My Home Assistant to be set up):

1. HACS → Integrations → ⋮ → *Custom repositories*
2. Add the URL of this repository, category *Integration*
3. Install "EcoFlow Ocean 2", restart Home Assistant

### Manual

Copy the folder `custom_components/ecoflow_ocean2` into
`config/custom_components/` and restart Home Assistant.

Home Assistant 2024.10 or newer is required. From 2026.3 on, the integration
brings its own logo along (`brand/icon.png`); older versions show the generic
icon instead.

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

## Example automations

These are deliberately **not** built into the integration. They are personal
decisions — thresholds, wording, which messenger — and once baked into code
they are hard to adjust. As YAML they belong to you.

Every example below uses the entity IDs `sensor.powerocean_*`. Yours will differ
depending on what you named the device; look them up under *Settings → Devices
& Services → Entities*.

### Daily counters as a basis

Several examples need "today's" figures. Home Assistant does not derive those
from the kWh counters on its own — a `utility_meter` with a daily cycle does.
Add to `configuration.yaml`:

```yaml
utility_meter:
  ocean2_solar_daily:
    source: sensor.powerocean_solar_production
    cycle: daily
  ocean2_grid_import_daily:
    source: sensor.powerocean_grid_consumption
    cycle: daily
  ocean2_grid_export_daily:
    source: sensor.powerocean_grid_return
    cycle: daily
  ocean2_house_daily:
    source: sensor.powerocean_house_consumption_energy
    cycle: daily
```

### How long will the battery last?

Remaining energy divided by current consumption. The `availability` line is the
important part: without it the sensor would divide by zero at night and report
absurd runtimes.

```yaml
template:
  - sensor:
      - name: "Ocean 2 remaining runtime"
        unique_id: ocean2_remaining_runtime
        unit_of_measurement: h
        device_class: duration
        state_class: measurement
        availability: >
          {{ has_value('sensor.powerocean_battery_remaining_energy')
             and has_value('sensor.powerocean_house_consumption')
             and states('sensor.powerocean_house_consumption') | float(0) > 50 }}
        state: >
          {{ (states('sensor.powerocean_battery_remaining_energy') | float
              / states('sensor.powerocean_house_consumption') | float) | round(1) }}
```

### Self-sufficiency today

```yaml
template:
  - sensor:
      - name: "Ocean 2 self-sufficiency today"
        unique_id: ocean2_self_sufficiency_today
        unit_of_measurement: "%"
        state_class: measurement
        availability: >
          {{ has_value('sensor.ocean2_house_daily')
             and states('sensor.ocean2_house_daily') | float(0) > 0.1 }}
        state: >
          {% set house = states('sensor.ocean2_house_daily') | float %}
          {% set grid = states('sensor.ocean2_grid_import_daily') | float(0) %}
          {{ (100 * (house - grid) / house) | round(1) }}
```

### Sunset report

```yaml
automation:
  - alias: "Ocean 2 daily report at sunset"
    trigger:
      - trigger: sun
        event: sunset
    action:
      - action: notify.persistent_notification
        data:
          title: "Solar balance today"
          message: >
            Produced: {{ states('sensor.ocean2_solar_daily') | float(0) | round(1) }} kWh
            · House: {{ states('sensor.ocean2_house_daily') | float(0) | round(1) }} kWh
            · From grid: {{ states('sensor.ocean2_grid_import_daily') | float(0) | round(1) }} kWh
            · To grid: {{ states('sensor.ocean2_grid_export_daily') | float(0) | round(1) }} kWh
            · Battery now: {{ states('sensor.powerocean_battery') }} %
```

Swap `notify.persistent_notification` for your own service to get the report on
your phone — `notify.mobile_app_<your_device>`, for example.

### Warning at a low state of charge

```yaml
automation:
  - alias: "Ocean 2 battery low"
    trigger:
      - trigger: numeric_state
        entity_id: sensor.powerocean_battery
        below: 15
        for: "00:10:00"
    action:
      - action: notify.persistent_notification
        data:
          title: "Battery low"
          message: >
            Only {{ states('sensor.powerocean_battery') }} % left,
            house drawing {{ states('sensor.powerocean_house_consumption') }} W.
```

The `for:` is what makes this usable: without it a brief dip below the
threshold triggers a message, and you get one every few minutes.

### Connection loss

```yaml
automation:
  - alias: "Ocean 2 connection lost"
    trigger:
      - trigger: state
        entity_id: binary_sensor.powerocean_cloud_connection
        to: "off"
        for: "00:15:00"
    action:
      - action: notify.persistent_notification
        data:
          title: "Ocean 2 unreachable"
          message: "No data for 15 minutes."
```

**On detecting a power outage:** this cannot be done reliably with the data
available. It would be tempting to infer it from "grid at 0 W" — but that is
the normal state on a sunny day. What the device does *not* report is whether
the grid itself is present. During a real outage its cloud connection drops
too, so the automation above will fire — but so will it if only your internet
is down. Treat the message as "no contact", not as "power failure".

## Where the values come from

- **House consumption** is read from the device, which reports it balanced
  against solar, battery and grid in the same instant. Only when that field is
  missing does the integration fall back to a calculation — and that fallback
  comes out systematically low, because the fields it relies on are updated
  independently and therefore stem from different moments.
- **Total power across all phases** is the sum of the individual phases. It
  stays empty as long as one phase has not reported its value yet — a partial
  sum would be too low and therefore misleading.

> **What house consumption really means:** the device reports what your house
> draws *on top of* everything that feeds in behind its meter. If you run a
> second, unmetered source — a balcony solar unit, for example — its output
> never shows up, and the house consumption displayed is lower than what your
> house actually uses.

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

## A value looks wrong?

Then it is almost certainly the field mapping, not Home Assistant — this
generation sends in an undocumented message class, and a field can mean
something else on your system than on mine. That is how the worst bug so far
was found: what looked like the grid meter turned out to be a user's export
limit.

**[→ How to check values and capture raw data](DEBUGGING.md)**

The guide covers diagnostics, debug logging, what to note down from the app
alongside it, and a script that strips your serial number from the capture
before you post it.

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

## Support

I build this in my spare time and give it away. If it saves you something and you
can spare it, a small contribution is welcome — nothing is expected, and no
feature is gated behind it.

<a href="https://buymeacoffee.com/jensfr"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00?style=flat&logo=buymeacoffee&logoColor=black" alt="Buy me a coffee"></a>

A GitHub star costs nothing and helps just as much.

## License

MIT
