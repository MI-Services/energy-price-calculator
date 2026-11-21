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

Naming decision (18 nov 2026): visible tab titles are Dutch and
self-explanatory; no "EPC"/"EMS"/"Showroom" abbreviations in any visible title,
alt text or caption.

## Removed: Prijsgolf view (21 nov 2026)

The former `prijsgolf` view (24 hourly prices as ApexCharts bar chart with the
cheapest-20% band) was removed: the data was redundant with the Prijssensoren
view and the chart was not helpful. As a result the dashboard no longer uses the
`custom:apexcharts-card`, so the HA >= 2026.11 Marketplace requirement for
custom cards no longer applies to this dashboard (only native cards remain).
The ApexCharts/fallback documentation below is kept for history:

- The card was installed from the built-in **Marketplace** (HA >= 2026.11), with
  the card version pinned through its update entity; on older HA the
  provisioning fell back to a native `history-graph` with all 24 hourly sensors.
- Colors followed the webshop palette: duur `#d63638`, normaal `#C0762C`,
  goedkoop `#52796F`.
- Implementation notes (for reference): the axis key was `yaxis` (list) with a
  default `yaxis_id: prijs` via `all_series_config` and a hidden secondary axis
  `blok` for the band. Each hourly series used a `data_generator` plotting one
  point at the sensor's `starts_at` attribute with `parseFloat(state)`. The
  binary cheapest-20% sensor exposed only `rank` and `hour` (no `starts_at`),
  so the band deliberately did NOT use a `data_generator` and instead plotted
  recorder history as `type: area` + `curve: stepline` with a numeric
  `transform: "return x == 'on' ? 1 : 0;"`.

## Thin client

The dashboard only plots existing integration sensors
(`sensor.uurprijs_HH_00`, `sensor.huidige_uurprijs`,
`binary_sensor.goedkoopste_<pct>_van_de_dag`,
`sensor.goedkoopste_uren_morgen_<pct>`). No price logic lives in HA.
