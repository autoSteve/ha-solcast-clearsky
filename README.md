# Solcast Clear Sky

Companion integration for `solcast_solar` that estimates clear-sky PV generation using a Bird Clear Sky Model implementation with free OpenWeatherMap atmospheric forecast data.

"Clear-sky" here means cloud effects are removed. The model estimates what configured Solcast sites could produce under clear sky, while still accounting for atmospheric attenuation.

## What this integration does

- Reads your configured `solcast_solar` sites (capacity, tilt, azimuth, loss factor, site latitude).
- Fetches OpenWeatherMap 5-day / 3-hour forecast data for your Home Assistant location.
- Interpolates atmospheric values to 30-minute steps.
- Computes per-site clear-sky output and a combined total across all sites.
- Exposes daily energy sensors plus optional interval/site breakdown attributes.

Update cadence:

- Forecast refresh every hour.
- If no Solcast sites are currently available, retries every 5 seconds until they are.

## Model inputs and assumptions

The calculation uses:

- Relative air mass (Kasten-Young approximation).
- Ozone thickness approximation based on latitude and day-of-year.
- Water vapor estimate from forecast temperature and humidity.
- A simple aerosol optical depth proxy derived from OWM weather codes.
- Plane-of-array irradiance using each site's tilt and azimuth.

Important limitations:

- This is a practical approximation, not a confident yield model.
- Atmospheric inputs come from a free weather forecast feed, not specialised irradiance datasets.
- Results are useful for trend/relative planning, not for high-grade forecasting.

## Prerequisites

- `solcast_solar` integration already configured with at least one site.
- OpenWeatherMap API key (free tier works for this integration's usage).

## Installation

Install as a custom integration (for example via HACS using a custom repository https://github.com/autoSteve/ha-solcast-clearsky) or manually, then restart Home Assistant.

## Configuration

Add integration:

1. Go to **Settings > Devices & Services > Add Integration**.
2. Search for **Solcast Clear Sky**.
3. Enter your OpenWeatherMap API key.

Validation behavior:

The setup flow checks your API key against the OpenWeatherMap forecast endpoint. Setup is blocked if `solcast_solar` is not configured first.

## Entities

The integration creates daily combined energy sensors (device class `energy`, unit `kWh`):

- `Today`
- `Tomorrow`
- Additional days as `D3`, `D4`, ... based on Solcast future day availability

Each entity represents the combined clear-sky kWh across all discovered Solcast sites for that day.

## Options

Options control sensor attributes exposed on each day entity:

- `Half-hourly detail` (default: on): adds `detailedForecast`
- `Hourly detail` (default: off): adds `detailedHourly`
- `By site` (default: off): adds per-site day totals keyed by normalized site id

Site keys are normalized to lowercase with hyphens replaced by underscores.

## Attribute schema

When enabled:

- `detailedForecast`: list of 30-minute intervals
- `detailedHourly`: list of hourly intervals aggregated from half-hourly values

Interval item format:

```json
{
    "period_start": "2026-06-16T09:00:00+00:00",
    "pv_clearsky": 2.137
}
```

`pv_clearsky` is average power in kW during that interval.

## Service: query_clear_sky_data

Service name:

- `solcast_clearsky.query_clear_sky_data`

Supports response data (`supports_response: only`) and returns combined or per-site clear-sky data.

### Inputs

- `site` (optional): Solcast site id, hyphen or underscore form accepted
- `start_date_time` (optional): datetime lower bound for interval filtering
- `end_date_time` (optional): datetime upper bound for interval filtering

Note that `start_date_time` and `end_date_time` influence the period of detailed responses. All available combined day values are returned regardless of the range specified.

### Combined example

```yaml
service: solcast_clearsky.query_clear_sky_data
data:
    start_date_time: "2026-06-16T00:00:00Z"
    end_date_time: "2026-06-16T12:00:00Z"
response_variable: clearsky
```

Response shape:

```json
{
    "data": {
        "day_count": 2,
        "combined": {
            "0": 32.184,
            "1": 28.931
        },
        "detailedForecast": [
            { "period_start": "2026-06-16T00:00:00+00:00", "pv_clearsky": 0.0 }
        ],
        "detailedHourly": [
            { "period_start": "2026-06-16T00:00:00+00:00", "pv_clearsky": 0.0 }
        ],
        "start_date_time": "2026-06-16T00:00:00+00:00",
        "end_date_time": "2026-06-16T11:30:00+00:00"
    }
}
```

### Per-site example

```yaml
service: solcast_clearsky.query_clear_sky_data
data:
    site: "1234-5678-9012-3456"
response_variable: clearsky_site
```

Returns:

- `site_id`
- `forecasts` (daily kWh map by day index)
- `detailedForecast`
- `detailedHourly`
- `start_date_time` and `end_date_time`

## Troubleshooting

- `solcast_solar_not_configured`: configure Solcast Solar first.
- `auth` during setup: invalid OpenWeatherMap API key.
- `connection` during setup/update: OpenWeatherMap endpoint unreachable.
- No site data yet: integration keeps retrying until Solcast sites are available.
