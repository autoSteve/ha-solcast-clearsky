# Solcast Clear Sky Companion

A companion integration for `ha-solcast-solar` that generates a weather-attenuated, proxy clear-sky photovoltaic forecast for your solar array.

## Why is this needed?

The official Solcast API endpoints provided for legacy hobbyist accounts do not include `clearsky_estimate` data. This poses a challenge for users relying on advanced energy prediction software (like Predbat) to calculate inverter clipping and theoretical maximum generation. 

This custom component elegantly bypasses this limitation. It reads your array configurations directly from the `solcast_solar` integration, pulls atmospheric conditions via the OpenWeatherMap API, and computes a detailed proxy clear-sky forecast locally using the **Bird Clear Sky Model**.

## How it works

1. **Zero Configuration**: It dynamically extracts your array geometry (tilt, azimuth, capacity, efficiency) directly from your `ha-solcast-solar` configuration entries.
2. **Atmospheric Attenuation**: It uses the free OpenWeatherMap API to retrieve temperature, humidity, and weather conditions for your Home Assistant location.
3. **Advanced Modeling**: It calculates Precipitable Water, Ozone Thickness (Van Heuklon), and Aerosol Optical Depth (AOD) to build an accurate Plane of Array (POA) irradiance profile that mimics the Solcast API payload structure.

## Installation

### HACS (Home Assistant Community Store)
1. Open HACS in Home Assistant.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add the URL of this repository and select the category **Integration**.
4. Click **Download** to install the `solcast_clearsky` integration.
5. Restart Home Assistant.

### Manual Installation
1. Download the `custom_components/solcast_clearsky` folder from this repository.
2. Copy it into your Home Assistant's `custom_components` directory.
3. Restart Home Assistant.

## Configuration

**Prerequisites:**
1. You must already have the `ha-solcast-solar` integration installed and configured.
2. You must have a free OpenWeatherMap API key (Standard 3-hour forecast API).

**Setup:**
1. Navigate to **Settings** -> **Devices & Services** -> **Add Integration**.
2. Search for **Solcast Clear Sky**.
3. Enter your OpenWeatherMap API Key.
4. Select the breakdown attributes you wish to expose (Hourly, Half-Hourly, Per-Site).

## Entities

The integration will create combined clear-sky sensors representing the sum of your PV arrays for each forecasted day:

- `sensor.solcast_clearsky_forecast_today`
- `sensor.solcast_clearsky_forecast_tomorrow`
- `sensor.solcast_clearsky_forecast_d3`

These entities contain a `detailedForecast` attribute identical in structure to the `ha-solcast-solar` sensors, enabling seamless drop-in replacements for third-party tools.
