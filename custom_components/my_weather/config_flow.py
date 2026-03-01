from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import selector

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_API_KEYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_LANGUAGE,
    DEFAULT_LANGUAGE,
)

CONF_API_KEY_1 = "api_key_1"
CONF_API_KEY_2 = "api_key_2"
CONF_API_KEY_3 = "api_key_3"
CONF_API_KEY_4 = "api_key_4"

_TEXT_SELECTOR = selector({"text": {"type": "text"}})


class MeteonomiqsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 3

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}

        if user_input is not None:

            # Collect the 4 individual key fields into api_keys list
            keys = []
            for field in (CONF_API_KEY_1, CONF_API_KEY_2, CONF_API_KEY_3, CONF_API_KEY_4):
                val = (user_input.get(field) or "").strip()
                if val and val not in keys:
                    keys.append(val)

            # Legacy fallback: single api_key field
            if not keys and user_input.get(CONF_API_KEY):
                keys = [user_input[CONF_API_KEY].strip()]

            if not keys:
                errors[CONF_API_KEY_1] = "required"

            # Convert lat/lon from string to float and validate
            lat = None
            lon = None
            try:
                lat = float(str(user_input.get(CONF_LATITUDE, "")).replace(",", "."))
                if not -90 <= lat <= 90:
                    raise ValueError
                user_input[CONF_LATITUDE] = lat
            except (ValueError, TypeError):
                errors[CONF_LATITUDE] = "invalid_lat"

            try:
                lon = float(str(user_input.get(CONF_LONGITUDE, "")).replace(",", "."))
                if not -180 <= lon <= 180:
                    raise ValueError
                user_input[CONF_LONGITUDE] = lon
            except (ValueError, TypeError):
                errors[CONF_LONGITUDE] = "invalid_lon"

            if not errors:
                unique_id = f"{lat:.3f}_{lon:.3f}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                data = {
                    CONF_API_KEYS: keys,
                    CONF_LATITUDE: lat,
                    CONF_LONGITUDE: lon,
                    CONF_LANGUAGE: user_input.get(CONF_LANGUAGE, DEFAULT_LANGUAGE),
                }
                title = f"Meteonomiqs ({lat}, {lon})"
                return self.async_create_entry(title=title, data=data)

        data_schema = vol.Schema({
            vol.Required(CONF_API_KEY_1): _TEXT_SELECTOR,
            vol.Optional(CONF_API_KEY_2): _TEXT_SELECTOR,
            vol.Optional(CONF_API_KEY_3): _TEXT_SELECTOR,
            vol.Optional(CONF_API_KEY_4): _TEXT_SELECTOR,
            vol.Required(CONF_LATITUDE): _TEXT_SELECTOR,
            vol.Required(CONF_LONGITUDE): _TEXT_SELECTOR,
            vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): selector({
                "select": {
                    "options": [
                        {"value": "de", "label": "Deutsch"},
                        {"value": "en", "label": "English"},
                        {"value": "fr", "label": "Français"},
                        {"value": "it", "label": "Italiano"},
                        {"value": "es", "label": "Español"},
                    ]
                }
            }),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
