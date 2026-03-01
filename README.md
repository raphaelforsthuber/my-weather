# my-weather

A custom Home Assistant integration for the [Meteonomiqs](http://www.wetter.com) weather API. Provides current conditions, hourly forecasts, and daily forecasts as HA entities — including a full `weather` entity usable in the standard weather card.

> **Important:** The Meteonomiqs free tier allows only **50 API calls per key per month**. This integration does **not** poll automatically. You must trigger updates manually via an automation.

---
Use https://github.com/mlamberts78/weather-chart-card (HACS) or original HA weather card to show the data called by my-weather.

<img width="506" height="662" alt="image" src="https://github.com/user-attachments/assets/5f2bfa8f-0c91-4d6b-a67d-75b1cc812603" />




## Features

- Up to **4 API keys** with automatic round-robin rotation on rate-limit (HTTP 429)
- **Manual update** via the `my_weather.update` service — full control over your API quota
- Persistent cache: data survives HA restarts without an extra API call
- Current index recalculated every 5 minutes from cached data (no extra call)
- Supports **DE / EN / FR / IT / ES** weather descriptions from the API
- Full `weather` entity + individual sensor entities

---

## API Quota & Key Rotation

The Meteonomiqs free tier gives you **50 calls per API key per month**.

| Keys configured | Monthly calls available |
|:-:|:-:|
| 1 | 50 |
| 2 | 100 |
| 3 | 150 |
| 4 | 200 |

The integration rotates to the next key automatically when the API returns HTTP 429 (rate limit exceeded). The currently active key index is exposed as a diagnostic sensor.

### Recommended Automation

Since auto-polling is disabled, you control **when** to fetch. A sensible setup for 1 key (50 calls/month ≈ 1–2 per day):

```yaml
automation:
  - alias: "Meteonomiqs – daily weather update"
    trigger:
      - platform: time
        at: "06:00:00"
      - platform: time
        at: "13:00:00"
    action:
      - service: my_weather.update
```

With 2 keys (100 calls/month) you can update up to 3× per day, and so on. Adjust to your needs — just stay within your quota.

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/my-weather/my-weather` as type **Integration**
3. Install **my-weather** and restart Home Assistant

### Manual

1. Copy the `custom_components/my_weather/` folder into your HA `custom_components/` directory
2. Restart Home Assistant

---

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **Meteonomiqs**.

| Field | Description |
|---|---|
| API Key 1 | Required. Your Meteonomiqs API key. |
| API Key 2–4 | Optional. Additional keys for higher monthly quota. |
| Latitude | Location latitude (e.g. `48.2083`) |
| Longitude | Location longitude (e.g. `16.3731`) |
| Language | Language for weather descriptions: DE / EN / FR / IT / ES |

Get your API key at https://www.meteonomiqs.com/weather-api/#heading-price-packages_2

---

## Entities

### Weather Entity

| Entity | Description |
|---|---|
| `weather.my_weather` | Standard HA weather entity with current conditions and forecast |

### Current Conditions (Sensors)

These reflect the **current hour** from the cached forecast data.

| Entity | Unit | Description |
|---|---|---|
| `sensor.my_weather_current_temperature` | °C | Current temperature |
| `sensor.my_weather_current_humidity` | % | Relative humidity |
| `sensor.my_weather_current_cloud_coverage` | % | Cloud coverage |
| `sensor.my_weather_current_wind_speed` | km/h | Wind speed |
| `sensor.my_weather_current_wind_gusts` | km/h | Wind gusts |
| `sensor.my_weather_current_precipitation` | mm | Precipitation |

### Hourly Forecast (Sensors)

8 sensors covering the **next 0–7 hours** relative to the current hour. State = HA weather condition string.

| Entity | Description |
|---|---|
| `sensor.my_weather_forecast_0h` | Current hour |
| `sensor.my_weather_forecast_1h` | +1 hour |
| … | … |
| `sensor.my_weather_forecast_7h` | +7 hours |

**Attributes per hourly sensor:**

| Attribute | Description |
|---|---|
| `hour_local` | Local time (e.g. `14:00`) |
| `temperature` | Temperature in °C |
| `precipitation` | Precipitation in mm |
| `cloud_coverage` | Cloud coverage in % |
| `wind_speed` | Wind speed in km/h |
| `wind_gust` | Wind gusts in km/h |

### Daily Forecast (Sensors)

7 sensors covering **today + 6 days**. State = HA weather condition string (weighted by severity across all hours of the day).

| Entity | Description |
|---|---|
| `sensor.my_weather_day_0` | Today |
| `sensor.my_weather_day_1` | Tomorrow |
| … | … |
| `sensor.my_weather_day_6` | +6 days |

**Attributes per daily sensor:**

| Attribute | Description |
|---|---|
| `date` | Date (YYYY-MM-DD) |
| `temp_max` | Maximum temperature in °C |
| `temp_min` | Minimum temperature in °C |
| `precipitation` | Total precipitation in mm |
| `cloud_coverage` | Average cloud coverage in % |
| `wind_speed` | Average wind speed in km/h |
| `wind_gust_max` | Maximum wind gusts in km/h |
| `wind_warning` | `true` if significant wind warning for that day |

### Diagnostic Sensors

| Entity | Description |
|---|---|
| `sensor.my_weather_last_api_update` | Timestamp of last successful API call |
| `sensor.my_weather_data_age` | Age of current data in minutes |
| `sensor.my_weather_monthly_api_calls` | Total API calls made this month (across all keys) |
| `sensor.my_weather_api_status` | `OK` / `Warning` (≥80 calls) / `Limit reached` (≥100 calls) |
| `sensor.my_weather_active_api_key` | Index (1–4) of the currently active API key |

---

## Services

| Service | Description |
|---|---|
| `my_weather.update` | Manually trigger a fresh API fetch. Use this in automations to control your quota. |

---

## License

MIT License — see [LICENSE](LICENSE)
