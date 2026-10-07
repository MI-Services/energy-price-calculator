# Home Assistant Dynamic Energy Price Calculator

Shows your dynamic electricity prices in Home Assistant and tells you when
energy is cheapest, so you can run devices at the right moment.

This integration is a thin display client for the Dynamic Energy Pricing
platform. All price calculation (taxes, supplier surcharges, ranking) happens
on the server, so supplier changes and fixes reach you without updating this
component. It fetches the finished prices and ranks from the server API and
computes nothing itself.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MI-Services&repository=energy-price-calculator&category=integration)

## Functionality

- Current hour price (your supplier consumer price, taxes included)
- 24 hourly price sensors (one per local hour)
- Percentage binary sensors: ON while the current hour is among the cheapest
  10% .. 90% of the day (floor semantics: a sensor is never ON for more than
  its percentage of the day)
- Your supplier is determined server-side via your API key (no local tariff
  configuration)
- One API request per day: a shared coordinator fetches the whole day once
  (at 00:05 local time, retrying every 30 minutes on failure). Hour-to-hour
  state changes are computed locally without further requests

## Installation

HACS is optional but recommended (easy updates). This repository is not in the
HACS default list, so it is added as a custom repository.

### Via HACS

1. Install [HACS](https://hacs.xyz/docs/use/) if you haven't already
2. Click the badge above, or in HACS: ⋮ -> **Custom repositories** -> add
   `https://github.com/MI-Services/energy-price-calculator` with type
   **Integration**
3. Download **Energy Price Calculator** in HACS and restart Home Assistant

### Manually (without HACS)

1. Copy `custom_components/energy_price_calculator/` into your Home
   Assistant configuration directory
2. Restart Home Assistant

### Configuration

1. Settings -> Devices & services -> Add integration -> **Dynamic Energy
   Price Calculator**
2. Fill in:
   - **Server URL**: e.g. `https://api.mijservices.nl`
   - **API key**: your personal key (via MI Services)
3. The integration validates the key immediately against `/api/v1/me`

## Sensors

- `sensor.huidige_uurprijs` - current consumer price (EUR/kWh)
- `sensor.uurprijs_uu_00` - 24 sensors, one per hour
- `binary_sensor.goedkoopste_10_van_de_dag` .. `..._90_van_de_dag` - ON when
  the current hour is in the cheapest X% of the day (rank vs the day
  interval count; identical semantics for hourly and future quarter-hour
  tariffs)

### Automation example

```yaml
automation:
  - alias: "EV charging in the cheapest 10% of hours"
    trigger:
      - platform: state
        entity_id: binary_sensor.goedkoopste_10_van_de_dag
        to: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.skoda_enyaq_opladen
```

## Blueprints

This component ships ready-to-use [Home Assistant blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/)
so you don't have to write automations by hand.

### Run device during cheapest hours

Turns a device on while the current hour is among the cheapest of the day,
and off otherwise. Only two inputs: your price-category sensor and the
switch to control.

Import it in Home Assistant:

> **Settings → Automations & Scenes → ⋮ (top right) → Import blueprint**

and paste this URL:

```
https://raw.githubusercontent.com/MI-Services/energy-price-calculator/refs/heads/main/blueprints/automation/energy_price_calculator/run_device_during_cheapest_hours.yaml
```

Or install manually by placing the file in:

```
<config>/blueprints/automation/energy_price_calculator/
```

After importing, create an automation from the blueprint
(*Create automation → Blueprints → Run Device During Cheapest Hours*),
select your `energy_price_calculator` category sensor and the appliance switch — done.

## Attributes

- `market_price` - market price (EUR/kWh)
- `consumer_price` - your consumer price (calculated server-side)
- `rank` - rank of this hour within today (1 = cheapest, 24 = most expensive)
- `starts_at` - hour start (UTC, ISO 8601)

No `tax_breakdown` and no derived cheap/expensive flags: price composition
and classification are server-side; this component only displays.

## Design choices

- **Thin client:** no tax/tariff calculation and no percentile/rank
  calculation locally; the server provides `consumer_price` and `rank`.
- **No price-source clients:** the server fetches market prices (with
  failover between sources), so this component never talks to Frank Energie,
  ENTSO-e or similar services directly.
- **Low request volume:** one request per day per installation; the
  server rate is therefore predictable.
- **No "cheapest hours" sensor:** it can be derived from the percentage binary
  sensors.

## Live check outside HA

    python scripts/check_api_live.py http://localhost:8000 demo-key-1

## Development

    pip install -e ".[dev]"
    pytest
