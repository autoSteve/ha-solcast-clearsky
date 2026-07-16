"""Bird Clear Sky Model implementation for PV power forecasting.

Computes weather-attenuated clear-sky irradiance for each 30-minute interval,
using OpenWeatherMap atmospheric data for AOD/humidity/temperature correction.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import TYPE_CHECKING, Any

from astral.sun import azimuth as astral_azimuth, elevation as astral_elevation

if TYPE_CHECKING:
    from astral.observer import Observer


def _calculate_ozone(lat: float, day_of_year: int) -> float:
    """Van approximation for vertical ozone layer thickness (cm-atm)."""
    lat_rad = math.radians(lat)
    j_idx = 360.0 * (day_of_year - 80) / 365.25
    j_rad = math.radians(j_idx)
    ozone = 0.235 + (0.150 + 0.040 * math.sin(lat_rad) * math.sin(j_rad)) * (math.sin(1.28 * lat_rad) ** 2)
    return max(0.2, ozone)


def _get_interpolated_atmos(target_time: datetime, atmos_timeline: dict[datetime, dict[str, float]]) -> dict[str, float]:
    """Linearly interpolate 3-hour atmospheric blocks to exact 30-minute steps."""
    target_naive = target_time.replace(tzinfo=None) if target_time.tzinfo is not None else target_time
    sorted_times = sorted(atmos_timeline.keys())

    if not sorted_times:
        return {"temp": 20.0, "rh": 50.0, "aod": 0.1}
    if target_naive <= sorted_times[0]:
        return atmos_timeline[sorted_times[0]]
    if target_naive >= sorted_times[-1]:
        return atmos_timeline[sorted_times[-1]]

    lower_index = 0
    for i, boundary in enumerate(sorted_times):
        if boundary > target_naive:
            lower_index = i - 1
            break

    t1 = sorted_times[lower_index]
    t2 = sorted_times[lower_index + 1]
    fraction = (target_naive - t1).total_seconds() / (t2 - t1).total_seconds()
    p1, p2 = atmos_timeline[t1], atmos_timeline[t2]
    return {
        "temp": p1["temp"] + fraction * (p2["temp"] - p1["temp"]),
        "rh": p1["rh"] + fraction * (p2["rh"] - p1["rh"]),
        "aod": p1["aod"] + fraction * (p2["aod"] - p1["aod"]),
    }


def build_atmos_timeline(owm_data: dict[str, Any]) -> dict[datetime, dict[str, float]]:
    """Parse OWM 5-day/3-hour forecast JSON into an atmosphere timeline dict.

    Keys are naive UTC datetimes; values contain temp (°C), rh (%), and aod (proxy).
    """
    timeline: dict[datetime, dict[str, float]] = {}
    for item in owm_data.get("list", []):
        dt_utc = datetime.utcfromtimestamp(item["dt"])

        temp_c = float(item["main"]["temp"])
        rh_pct = float(item["main"]["humidity"])
        weather_id = int(item["weather"][0]["id"])

        # 7xx series = atmospheric obscuration (haze, dust, smoke, ash, mist)
        aod_500 = 0.35 if 701 <= weather_id <= 781 else 0.10

        timeline[dt_utc] = {"temp": temp_c, "rh": rh_pct, "aod": aod_500}

    return timeline


def compute_site_clearsky(
    astral_observer: Observer,
    atmos_timeline: dict[datetime, dict[str, float]],
    start_time: datetime,
    days: int,
    capacity_kw: float,
    efficiency: float,
    tilt: float,
    azimuth: float,
    lat: float,
) -> tuple[dict[int, float], dict[int, list[dict[str, str | float]]]]:
    """Compute daily clear-sky totals and half-hourly breakdowns.

    Returns:
        tuple[dict[int, float], dict[int, list[dict[str, str | float]]]]:
            1) day_index (0=today, 1=tomorrow, …) to kWh total
            2) day_index to half-hourly list with period_start and pv_clearsky (kW average over the interval)
    """
    tilt_rad = math.radians(tilt)
    surf_az_rad = math.radians(azimuth)

    # Accumulate kWh per day_index
    daily_kwh: dict[int, float] = dict.fromkeys(range(days), 0.0)
    halfhourly: dict[int, list[dict[str, str | float]]] = {day_index: [] for day_index in range(days)}

    total_intervals = days * 48
    current_start = start_time

    for _ in range(total_intervals):
        midpoint = current_start + timedelta(minutes=15)
        day_index = (midpoint.date() - start_time.date()).days
        if day_index >= days:
            current_start += timedelta(minutes=30)
            continue

        day_of_year = midpoint.timetuple().tm_yday

        solar_elevation_val = astral_elevation(astral_observer, midpoint)
        solar_azimuth_val = astral_azimuth(astral_observer, midpoint)

        elev_rad = math.radians(solar_elevation_val)
        az_rad = math.radians(solar_azimuth_val)

        if elev_rad <= 0:
            halfhourly[day_index].append(
                {
                    "period_start": current_start.isoformat(),
                    "pv_clearsky": 0.0,
                }
            )
            current_start += timedelta(minutes=30)
            continue

        zenith_rad = (math.pi / 2) - elev_rad
        cos_zenith = math.cos(zenith_rad)

        # Kasten-Young relative air mass
        air_mass = 1.0 / (cos_zenith + 0.15 * ((solar_elevation_val + 3.885) ** -1.253))

        atmos = _get_interpolated_atmos(midpoint, atmos_timeline)

        # Precipitable water vapour (cm) via Tetens / partial pressure equations
        sat_vp = 0.61078 * math.exp((17.27 * atmos["temp"]) / (atmos["temp"] + 237.3))
        actual_vp = (atmos["rh"] / 100.0) * sat_vp
        # Guard against log(0) for very dry conditions
        if actual_vp <= 0:
            actual_vp = 1e-6
        dewpoint = (237.3 * math.log(actual_vp / 0.61078)) / (17.27 - math.log(actual_vp / 0.61078))
        precipitable_water = math.exp(0.1133 - math.log(3.1) + 0.0393 * dewpoint)

        ozone = _calculate_ozone(lat, day_of_year)

        # Bird Clear Sky Model transmittance components
        t_r = math.exp(-0.008735 * (air_mass**0.608))
        t_g = math.exp(-0.0117 * (air_mass**0.41))

        oz_am = ozone * air_mass
        t_o = 1.0 - (
            0.1611 * oz_am * ((1.0 + 139.48 * oz_am) ** -0.3035) - 0.002715 * oz_am * ((1.0 + 0.044 * oz_am + 0.0003 * (oz_am**2)) ** -1)
        )

        pw_am = precipitable_water * air_mass
        t_w = 1.0 - 2.4959 * pw_am / (((1.0 + 79.034 * pw_am) ** 0.6828) + 6.385 * pw_am)

        t_a = math.exp(-(atmos["aod"] ** 0.81) * (air_mass**0.612))

        solar_constant = 1367.0  # W/m²
        dni = 0.9662 * solar_constant * t_r * t_g * t_o * t_w * t_a
        dhi = 0.79 * solar_constant * cos_zenith * t_g * t_o * t_w * (1.0 - t_a) / (1.0 - air_mass + (air_mass**1.02))

        # Plane-of-array irradiance
        cos_aoi = max(
            0.0,
            cos_zenith * math.cos(tilt_rad) + math.sin(zenith_rad) * math.sin(tilt_rad) * math.cos(az_rad - surf_az_rad),
        )
        poa = (dni * cos_aoi) + (dhi * ((1.0 + math.cos(tilt_rad)) / 2.0))

        # Convert irradiance → power for this 30-minute slot (kWh = kW × 0.5 h)
        pv_kw = max(0.0, (poa / 1000.0) * capacity_kw * efficiency)
        interval_kwh = pv_kw * 0.5  # 30-min slot
        daily_kwh[day_index] = daily_kwh[day_index] + interval_kwh
        halfhourly[day_index].append(
            {
                "period_start": current_start.isoformat(),
                "pv_clearsky": round(pv_kw, 3),
            }
        )

        current_start += timedelta(minutes=30)

    return ({k: round(v, 3) for k, v in daily_kwh.items()}, halfhourly)
