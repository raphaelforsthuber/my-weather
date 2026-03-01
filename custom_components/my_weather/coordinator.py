from __future__ import annotations

import logging
from datetime import timedelta
from collections import Counter

from aiohttp import ClientTimeout
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from .weather import map_condition_from_state

from .const import API_BASE, LANG_MAP

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

class MeteonomiqsDataUpdateCoordinator(DataUpdateCoordinator):
    """Meteonomiqs Update Coordinator."""

    def __init__(self, hass, api_keys, latitude, longitude, language):
        super().__init__(
            hass,
            _LOGGER,
            name="MeteonomiqsDataUpdateCoordinator",
            update_interval=None,
        )

        self.hass = hass
        self.api_keys = list(api_keys)
        self._current_key_index = 0
        self.latitude = latitude
        self.longitude = longitude
        self.language = language

        self.last_successful_update = None
        self.monthly_call_counter = 0
        self.current_month = dt_util.utcnow().month
        self.data = None

        lat_key = self._normalize(latitude)
        lon_key = self._normalize(longitude)

        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"my_weather_stats_{lat_key}_{lon_key}",
        )
        self._stats_loaded = False

        async_track_time_interval(
            hass,
            self._async_tick_recalculate_current_index,
            timedelta(minutes=5),
        )

    @staticmethod
    def _normalize(value):
        try:
            return f"{float(value):.4f}"
        except Exception:
            return str(value)

    @property
    def api_key(self) -> str:
        return self.api_keys[self._current_key_index]

    @property
    def current_key_index(self) -> int:
        return self._current_key_index

    async def _switch_api_key_and_clear_cache(self) -> None:
        if not self.api_keys:
            return

        self._current_key_index = (self._current_key_index + 1) % len(self.api_keys)
        _LOGGER.warning("Meteonomiqs: HTTP 429 → switching API key to index %s", self._current_key_index)

        self.data = None
        self.last_successful_update = None
        await self._store.async_remove()
        self._stats_loaded = False
        self.async_set_updated_data(self.data)

    async def _async_load_stats(self):
        if self._stats_loaded:
            return
        stored = await self._store.async_load()
        if stored:
            self.monthly_call_counter = stored.get("monthly_call_counter", 0)
            self.current_month = stored.get("current_month", self.current_month)
            ts = stored.get("last_successful_update")
            if ts:
                try:
                    self.last_successful_update = dt_util.parse_datetime(ts)
                except Exception:
                    self.last_successful_update = None
            self.data = stored.get("last_data")
        self._stats_loaded = True

    async def _async_save_stats(self):
        await self._store.async_save({
            "monthly_call_counter": self.monthly_call_counter,
            "current_month": self.current_month,
            "last_successful_update": (
                self.last_successful_update.isoformat()
                if self.last_successful_update else None
            ),
            "last_data": self.data,
        })

    async def async_config_entry_first_refresh(self):
        await self._async_load_stats()
        if self.data and self.last_successful_update:
            _LOGGER.info("Meteonomiqs: using cached data on startup")
            self.async_set_updated_data(self.data)
            return
        await super().async_config_entry_first_refresh()

    def _recalculate_current_index(self) -> bool:
        if not self.data:
            return False
        hourly = self.data.get("hourly") or []
        now = dt_util.utcnow()
        for idx, h in enumerate(hourly):
            start = dt_util.parse_datetime(h.get("from"))
            end = dt_util.parse_datetime(h.get("to"))
            if not start or not end:
                continue
            if start.tzinfo is None: start = start.replace(tzinfo=dt_util.UTC)
            if end.tzinfo is None: end = end.replace(tzinfo=dt_util.UTC)
            if start <= now < end:
                if self.data.get("current_index") != idx:
                    new_data = dict(self.data)
                    new_data["current_index"] = idx
                    new_data["current"] = hourly[idx]
                    self.data = new_data
                    self.async_set_updated_data(new_data)
                    return True
                break
        return False

    async def _async_tick_recalculate_current_index(self, now):
        self._recalculate_current_index()

    async def _async_update_data(self):
        await self._async_load_stats()
        now = dt_util.utcnow()
        url = f"{API_BASE}/forecast/{self.latitude}/{self.longitude}"

        if now.month != self.current_month:
            self.current_month = now.month
            self.monthly_call_counter = 0

        session = async_get_clientsession(self.hass)
        attempts = 0
        max_attempts = max(1, len(self.api_keys))
        raw = None

        while attempts < max_attempts:
            headers = {
                "x-api-key": self.api_key,
                "Accept": "application/json",
                "Accept-Language": LANG_MAP.get(self.language, "en-US"),
            }
            try:
                async with session.get(url, headers=headers, timeout=ClientTimeout(total=20)) as resp:
                    if resp.status == 429:
                        attempts += 1
                        await self._switch_api_key_and_clear_cache()
                        continue
                    if resp.status != 200:
                        raise UpdateFailed(f"HTTP {resp.status}")
                    raw = await resp.json()
                    break
            except Exception as err:
                raise UpdateFailed(f"Meteonomiqs fetch error: {err}")

        if raw is None:
            raise UpdateFailed("Meteonomiqs: all API keys returned HTTP 429")

        self.monthly_call_counter += 1
        hourly = raw.get("hourly") if isinstance(raw.get("hourly"), list) else []

        current_index = 0
        for idx, h in enumerate(hourly):
            start = dt_util.parse_datetime(h.get("from"))
            end = dt_util.parse_datetime(h.get("to"))
            if start and end:
                if start.replace(tzinfo=dt_util.UTC) <= now < end.replace(tzinfo=dt_util.UTC):
                    current_index = idx
                    break

        daily_map = {}
        for h in hourly:
            d = h.get("date")
            if d: daily_map.setdefault(d, []).append(h)

        WEIGHTS = {
            "clear-night": 0, "sunny": 5, "partlycloudy": 4, 
            "rainy": 3, "snowy": 3, "cloudy": 2, "fog": 1, "windy": 1
        }

        daily_list = []
        for d, hours in sorted(daily_map.items()):
            temps = [h.get("temperature", {}).get("avg") for h in hours if isinstance(h.get("temperature", {}).get("avg"), (int, float))]
            
            # Zustands-Logik
            hour_conditions = [
                map_condition_from_state(h.get("weather", {}).get("state"), False)
                for h in hours
            ]
            scores = {}
            for cond in hour_conditions:
                weight = WEIGHTS.get(cond, 1)
                scores[cond] = scores.get(cond, 0) + weight
            best_condition = max(scores, key=scores.get) if scores else "cloudy"

            # Niederschlag & Bewölkung
            prec_sum = sum(h.get("prec", {}).get("sum", 0.0) or h.get("prec", {}).get("amount", 0.0) for h in hours)
            cloud_vals = [h.get("clouds", {}).get("eights", 0) * 12.5 for h in hours if h.get("clouds", {}).get("eights") is not None]
            avg_clouds = round(sum(cloud_vals) / len(cloud_vals), 1) if cloud_vals else 0

            # Wind & Böen Aggregation (KORREKTUR)
            wind_avgs = [h.get("wind", {}).get("avg") for h in hours if isinstance(h.get("wind", {}).get("avg"), (int, float))]
            # Sammle alle Böen-Werte der Stunden
            gust_vals = [h.get("wind", {}).get("gusts", {}).get("value") for h in hours if h.get("wind", {}).get("gusts", {}).get("value") is not None]
            max_gust = max(gust_vals) if gust_vals else 0
            # Check ob IRGENDEINE Stunde eine Warnung hat
            is_significant = any(h.get("wind", {}).get("significantWind") for h in hours)

            daily_list.append({
                "date": d,
                "temperature": {
                    "min": min(temps) if temps else None,
                    "max": max(temps) if temps else None,
                },
                "prec": {"sum": round(prec_sum, 2)},
                "clouds": {"avg": avg_clouds},
                "weather": {
                    "state": best_condition
                },
                "wind": {
                    "avg": round(sum(wind_avgs) / len(wind_avgs), 1) if wind_avgs else 0,
                    "significantWind": is_significant,
                    "gusts": {"value": max_gust} # Exakt so wie in der sensor.py erwartet
                }
            })

        self.last_successful_update = now
        self.data = {
            "raw": raw,
            "hourly": hourly,
            "current": hourly[current_index] if hourly else None,
            "current_index": current_index,
            "daily": daily_list,
        }
        await self._async_save_stats()
        return self.data