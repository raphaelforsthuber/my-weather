from __future__ import annotations
from dataclasses import dataclass
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfTime,
    UnitOfPrecipitationDepth,
    PERCENTAGE,
    UnitOfSpeed,
    EntityCategory,
)
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .weather import map_condition_from_state

_LOGGER = logging.getLogger(__name__)

@dataclass
class MeteonomiqsPathSensorDescription(SensorEntityDescription):
    value_path: tuple[str, ...] = ()
    multiplier: float = 1.0

SENSORS: tuple[MeteonomiqsPathSensorDescription, ...] = (
    MeteonomiqsPathSensorDescription(
        key="temperature_current",
        name="Current Temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("temperature", "avg"),
    ),
    MeteonomiqsPathSensorDescription(
        key="humidity_current",
        name="Current Humidity",
        icon="mdi:water-percent",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("relativeHumidity",),
    ),
    MeteonomiqsPathSensorDescription(
        key="clouds_current",
        name="Current Cloud Coverage",
        icon="mdi:cloud-percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("clouds", "eights"),
        multiplier=12.5,
    ),
    MeteonomiqsPathSensorDescription(
        key="wind_speed_current",
        name="Current Wind Speed",
        icon="mdi:weather-windy",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("wind", "avg"),
    ),
    MeteonomiqsPathSensorDescription(
        key="wind_gust_current",
        name="Current Wind Gusts",
        icon="mdi:weather-windy-variant",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("wind", "gusts", "value"),
    ),
    MeteonomiqsPathSensorDescription(
        key="prec_sum_current",
        name="Current Precipitation",
        icon="mdi:weather-rainy",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("prec", "sum"),
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []

    for desc in SENSORS:
        entities.append(MeteonomiqsCurrentSensor(coord, entry, desc))

    entities.extend([
        MeteonomiqsLastApiUpdateSensor(coord),
        MeteonomiqsDataAgeSensor(coord),
        MeteonomiqsMonthlyCallCounter(coord),
        MeteonomiqsApiLimitWarning(coord),
        MeteonomiqsActiveApiKeyIndexSensor(coord, entry),
    ])

    for i in range(7):
        entities.append(MeteonomiqsDailyForecastSensor(coord, entry, i))

    for i in range(8):
        entities.append(MeteonomiqsHourlyForecastSensor(coord, entry, i))

    async_add_entities(entities)


class MeteonomiqsCurrentSensor(CoordinatorEntity, SensorEntity):
    entity_description: MeteonomiqsPathSensorDescription

    def __init__(self, coordinator, entry: ConfigEntry, description: MeteonomiqsPathSensorDescription):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = description.name

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        hourly = data.get("hourly", [])
        idx = data.get("current_index", 0)

        if not hourly or idx >= len(hourly):
            return None

        value = hourly[idx]
        for key in self.entity_description.value_path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if isinstance(value, (int, float)):
            value = round(value * self.entity_description.multiplier)
        return value


class MeteonomiqsHourlyForecastSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, offset: int):
        super().__init__(coordinator)
        self._offset = offset
        self._attr_unique_id = f"{entry.entry_id}_hourly_rel_{offset}"
        self._attr_name = f"Meteonomiqs Forecast +{offset}h"

    @property
    def _hour_data(self):
        data = self.coordinator.data or {}
        hourly = data.get("hourly", [])
        idx = data.get("current_index", 0)
        target_idx = idx + self._offset
        return hourly[target_idx] if target_idx < len(hourly) else None

    @property
    def native_value(self):
        hd = self._hour_data
        if not hd:
            return None
        w = hd.get("weather") or {}
        return map_condition_from_state(w.get("state"), hd.get("isNight"))

    @property
    def extra_state_attributes(self):
        hd = self._hour_data
        if not hd:
            return {}

        dt_str = hd.get("from")
        local_hour = ""
        if dt_str:
            dt = dt_util.parse_datetime(dt_str)
            if dt:
                local_hour = dt_util.as_local(dt).strftime("%H:00")

        wind = hd.get("wind", {})
        cloud_eights = hd.get("clouds", {}).get("eights")
        return {
            "hour_local": local_hour,
            "temperature": hd.get("temperature", {}).get("avg"),
            "precipitation": hd.get("prec", {}).get("sum"),
            "cloud_coverage": round(cloud_eights * 12.5) if cloud_eights is not None else None,
            "wind_speed": wind.get("avg"),
            "wind_gust": wind.get("gusts", {}).get("value"),
        }


class MeteonomiqsDailyForecastSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, offset: int):
        super().__init__(coordinator)
        self._offset = offset
        self._attr_unique_id = f"{entry.entry_id}_daily_rel_{offset}"
        self._attr_name = f"Meteonomiqs Day +{offset}"

    @property
    def _day_data(self):
        data = self.coordinator.data or {}
        daily = data.get("daily", [])
        return daily[self._offset] if self._offset < len(daily) else None

    @property
    def native_value(self):
        dd = self._day_data
        if not dd:
            return None
        return dd.get("weather", {}).get("state")

    @property
    def extra_state_attributes(self):
        hd = self._day_data
        if hd is None:
            return {}

        wind = hd.get("wind", {})
        return {
            "date": hd.get("date"),
            "temp_max": hd.get("temperature", {}).get("max"),
            "temp_min": hd.get("temperature", {}).get("min"),
            "precipitation": hd.get("prec", {}).get("sum"),
            "cloud_coverage": hd.get("clouds", {}).get("avg"),
            "wind_speed": wind.get("avg"),
            "wind_gust_max": wind.get("gusts", {}).get("value"),
            "wind_warning": wind.get("significantWind"),
        }


class MeteonomiqsLastApiUpdateSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "Meteonomiqs Last API Update"
    _attr_unique_id = "my_weather_last_api_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        ts = self.coordinator.last_successful_update
        return dt_util.as_utc(ts) if ts else None


class MeteonomiqsDataAgeSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "Meteonomiqs Data Age"
    _attr_unique_id = "my_weather_data_age"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        ts = self.coordinator.last_successful_update
        if not ts:
            return None
        return round((dt_util.utcnow() - ts).total_seconds() / 60)


class MeteonomiqsMonthlyCallCounter(CoordinatorEntity, SensorEntity):
    _attr_name = "Meteonomiqs Monthly API Calls"
    _attr_unique_id = "my_weather_api_calls_month"
    _attr_native_unit_of_measurement = "calls"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return getattr(self.coordinator, "monthly_call_counter", 0)


class MeteonomiqsApiLimitWarning(CoordinatorEntity, SensorEntity):
    _attr_name = "Meteonomiqs API Status"
    _attr_unique_id = "my_weather_api_limit_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        used = getattr(self.coordinator, "monthly_call_counter", 0)
        return "Limit reached" if used >= 100 else "Warning" if used >= 80 else "OK"


class MeteonomiqsActiveApiKeyIndexSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "Meteonomiqs Active API Key"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_active_api_key_index"

    @property
    def native_value(self):
        return int(getattr(self.coordinator, "current_key_index", 0)) + 1
