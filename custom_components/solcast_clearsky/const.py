"""Constants for solcast_clearsky."""

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final[str] = "solcast_clearsky"
SOLCAST_SOLAR_DOMAIN: Final[str] = "solcast_solar"
ATTRIBUTION: Final[str] = "Clear-sky data computed using Bird Clear Sky Model with OpenWeatherMap atmospheric data"

CONF_OWM_API_KEY: Final[str] = "owm_api_key"
SITE: Final[str] = "site"

ATTR_BRK_HALFHOURY: Final[str] = "attr_brk_halfhourly"
ATTR_BRK_HOURLY: Final[str] = "attr_brk_hourly"
ATTR_BRK_SITE: Final[str] = "attr_brk_site"
DETAILED_FORECAST: Final[str] = "detailedForecast"
DETAILED_HOURLY: Final[str] = "detailedHourly"

SERVICE_QUERY_CLEAR_SKY_DATA: Final[str] = "query_clear_sky_data"

OWM_FORECAST_URL: Final[str] = "https://api.openweathermap.org/data/2.5/forecast"
RETRY_INTERVAL_NO_SITES_SECONDS: Final[int] = 5

DEFAULT_SYSTEM_EFFICIENCY: Final[float] = 0.85
DEFAULT_ATTR_BRK_HALFHOURY: Final[bool] = True
DEFAULT_ATTR_BRK_HOURLY: Final[bool] = False
DEFAULT_ATTR_BRK_SITE: Final[bool] = False
