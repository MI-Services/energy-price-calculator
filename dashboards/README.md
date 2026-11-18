# Standard dashboard definition

`energy-price-calculator.yaml` in this directory is the single source of truth
for the standard **Energy Price Calculator** dashboard that every customer Pi
gets at provisioning.

## How provisioning consumes it

1. Fetch the pinned file from the *installed* integration release on the
   customer Pi (the integration is installed via the Marketplace, so the file
   versions along with integration releases).
2. Create the dashboard through the **Lovelace websocket API in storage mode**,
   in two steps:
   a. `lovelace/dashboards/create` with title "Energy Price Calculator",
      **`url_path: energy-price-calculator`**, `show_in_sidebar: true`,
      icon `mdi:currency-eur` — this registers the dashboard (title, sidebar
      entry, URL);
   b. `lovelace/config/save` with the **same `url_path`** to store the views
      from the YAML below.
   Always pass `url_path` explicitly on both calls: `lovelace/config/save`
   without a `url_path` targets the *default* dashboard (overwrite risk on a
   fresh Pi), and saving to an unregistered `url_path` fails with
   `config_not_found`. Never via a `lovelace:` block in `configuration.yaml` —
   YAML-mode dashboards are on the deprecation path.
3. Add the per-customer **dagrapport** view (hosted `rapport.svg` from the MI
   backend + notification history). This view is *not* in the public file: it
   depends on the MI backend and is provisioning-only.

## Views

| Tab (visible title) | Path | Content |
| --- | --- | --- |
| Prijssensoren | `prijssensoren` | All hourly price sensors of today + cheapest hours of tomorrow |
| Schakelpercentage | `schakelpercentage` | The 10-90% on/off sensors as tiles + explanation |
| Prijsgolf | `prijsgolf` | All 24 hourly prices of today as bars, colored per price category, cheapest-20% block highlighted |

Naming decision (18 nov 2026): visible tab titles are Dutch and
self-explanatory; no "EPC"/"EMS"/"Showroom" abbreviations in any visible title,
alt text or caption.

## Prijsgolf: ApexCharts + fallback

- HA >= 2026.11: the `custom:apexcharts-card` is installed from the built-in
  **Marketplace** (Settings > Marketplace). The provisioning pins the card
  version through its update entity, so a customer Pi always runs the pinned
  version (same version-pin policy as the webshop plugins). There is no HACS
  installation step (HACS is blocked as a separate install from 2026.11).
- HA < 2026.11 (no Marketplace custom cards): provisioning falls back to the
  native `history-graph` with all 24 hourly sensors (see the comment inside the
  prijsgolf view) — without the block highlight.

Colors follow the webshop palette: duur `#d63638`, normaal `#C0762C`,
goedkoop `#52796F`.

Implementation notes (prijsgolf card): the axis key is `yaxis` (list), with a
default `yaxis_id: prijs` via `all_series_config` and the hidden secondary
axis `blok` for the band. Each of the 24 hourly series uses a `data_generator`
that plots one point at the sensor's `starts_at` attribute with
`parseFloat(state)`, so bars land on the hour they represent instead of on
recorder state-change times. The binary cheapest-20% sensor exposes only
`rank` and `hour` (no `starts_at`), so the band deliberately does NOT use a
`data_generator` (a generator bypasses recorder history and would emit a
single point at `Date.now()`). Instead the band plots the binary sensor's
recorder history as `type: area` + `curve: stepline` with a numeric
`transform: "return x == 'on' ? 1 : 0;"` — raw on/off history states would
`parseFloat` to NaN and render as null. `group:` is not a supported series
key and is not used.

## Thin client

The dashboard only plots existing integration sensors
(`sensor.uurprijs_HH_00`, `sensor.huidige_uurprijs`,
`binary_sensor.goedkoopste_<pct>_van_de_dag`,
`sensor.goedkoopste_uren_morgen_<pct>`). No price logic lives in HA.

## Requirement

Customer Pis must run **HA >= 2026.11** before the provisioning feature rolls
out (Marketplace dependency). This is documented as a rollout dependency in the
deployment README of dynamic-energy-pricing.
