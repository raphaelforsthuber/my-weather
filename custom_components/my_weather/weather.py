from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.weather import (
    WeatherEntity,
    WeatherEntityFeature,
    Forecast,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfSpeed,
    UnitOfPressure,
    UnitOfPrecipitationDepth,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

def map_condition_from_state(state: int | None, is_night: bool = False) -> str:
    if state is None or state == -1:
        return "cloudy"
    if state == 0:
        return "clear-night" if is_night else "sunny"
    if state in (1, 2, 10, 20, 21):
        return "partlycloudy"
    if state in (3, 30):
        return "cloudy"
    if state in (4, 40, 45, 48, 49):
        return "fog"
    if state in (5, 51, 55, 56, 57, 6, 60, 61, 63, 66, 67, 8, 80, 81):
        return "rainy"
    if state in (65, 82):
        return "pouring"
    if state in (68, 69):
        return "snowy-rainy"
    if state in (7, 70, 71, 73, 75, 83, 84, 85, 86):
        return "snowy"
    if state in (9, 95, 96):
        return "lightning-rainy"
    return "cloudy"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([MeteonomiqsWeather(coordinator, entry)])

class MeteonomiqsWeather(CoordinatorEntity, WeatherEntity):
    _attr_has_entity_name = True
    _attr_name = "Meteonomiqs Weather"
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY |
        WeatherEntityFeature.FORECAST_HOURLY
    )
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_wind_gust_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_weather"

    @property
    def _cur(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("current", {})

    @property
    def condition(self) -> str | None:
        w = self._cur.get("weather", {})
        return map_condition_from_state(w.get("state"), self._cur.get("isNight", False))

    @property
    def native_temperature(self) -> float | None:
        return self._cur.get("temperature", {}).get("avg")

    @property
    def native_precipitation(self) -> float | None:
        p = self._cur.get("prec") or {}
        return p.get("amount") or p.get("sum")

    @property
    def humidity(self) -> float | None:
        return self._cur.get("relativeHumidity")

    @property
    def native_pressure(self) -> float | None:
        return self._cur.get("pressure")

    @property
    def native_wind_speed(self) -> float | None:
        return self._cur.get("wind", {}).get("avg")

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Neu: Aktuelle Windböen für die Weather Card."""
        return self._cur.get("wind", {}).get("gusts", {}).get("value")

    @property
    def wind_bearing(self) -> float | None:
        return self._cur.get("wind", {}).get("degree")

    @property
    def cloud_coverage(self) -> float | None:
        c = self._cur.get("clouds") or {}
        eights = c.get("eights")
        return round(eights * 12.5) if eights is not None else None

    # ------------------ DAILY ------------------
    async def async_forecast_daily(self) -> list[Forecast] | None:
        data = self.coordinator.data or {}
        daily = data.get("daily", [])
        if not daily: return None
        result = []
        for item in daily:
            d_str = item.get("date")
            dt_obj = dt_util.parse_datetime(f"{d_str}T12:00:00")
            if dt_obj: dt_obj = dt_util.as_utc(dt_obj)
            
            wind_group = item.get("wind", {})
            result.append({
                "datetime": dt_obj.isoformat() if dt_obj else d_str,
                "condition": item.get("weather", {}).get("state"),
                "native_temperature": item.get("temperature", {}).get("max"),
                "native_templow": item.get("temperature", {}).get("min"),
                "native_precipitation": item.get("prec", {}).get("sum"),
                "native_wind_speed": wind_group.get("avg"),
                "native_wind_gust_speed": wind_group.get("gusts", {}).get("value"),
                "wind_bearing": wind_group.get("degree"),
                "cloud_coverage": item.get("clouds", {}).get("avg"),
            })
        return result

    # ------------------ HOURLY ------------------
    async def async_forecast_hourly(self) -> list[Forecast] | None:
        data = self.coordinator.data or {}
        hourly = data.get("hourly", [])
        idx = data.get("current_index", 0)
        if not hourly: return None
        result = []
        for h in hourly[idx: idx + 48]:
            dt_obj = dt_util.parse_datetime(h.get("from"))
            if dt_obj: dt_obj = dt_util.as_utc(dt_obj)
            
            wind_group = h.get("wind", {})
            cloud_eights = h.get("clouds", {}).get("eights")
            result.append({
                "datetime": dt_obj.isoformat() if dt_obj else h.get("from"),
                "condition": map_condition_from_state(h.get("weather", {}).get("state"), h.get("isNight", False)),
                "native_temperature": h.get("temperature", {}).get("avg"),
                "native_precipitation": h.get("prec", {}).get("sum"),
                "native_wind_speed": wind_group.get("avg"),
                "native_wind_gust_speed": wind_group.get("gusts", {}).get("value"),
                "wind_bearing": wind_group.get("degree"),
                "cloud_coverage": round(cloud_eights * 12.5) if cloud_eights is not None else None,
            })
        return result

    @property
    def extra_state_attributes(self):
        last_update = getattr(self.coordinator, "last_successful_update", None)
        
        return {
            "last_api_update": last_update.isoformat() if last_update else None,
            "attribution": "Data provided by meteonomiqs.com",
        }
