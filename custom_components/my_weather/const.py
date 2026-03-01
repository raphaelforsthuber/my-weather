from homeassistant.const import Platform

DOMAIN = "my_weather"

CONF_API_KEY = "api_key"
CONF_API_KEYS = "api_keys"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_LANGUAGE = "language"

DEFAULT_LANGUAGE = "de"

PLATFORMS = [
    Platform.WEATHER,
    Platform.SENSOR,
]

API_BASE = "https://forecast.meteonomiqs.com/v4_0"

LANG_MAP = {
    "de": "de-DE",
    "en": "en-US",
    "fr": "fr-FR",
    "it": "it-IT",
    "es": "es-ES",
}
