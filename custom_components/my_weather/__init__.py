from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_API_KEY,
    CONF_API_KEYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_LANGUAGE,
)
from .coordinator import MeteonomiqsDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """YAML setup not used."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.debug("MY_WEATHER: async_setup_entry START – id=%s", entry.entry_id)

    hass.data.setdefault(DOMAIN, {})

    # Extract config
    # Accept new list-based config; fall back to legacy single key.
    api_keys = entry.data.get(CONF_API_KEYS)
    if not api_keys:
        legacy = entry.data.get(CONF_API_KEY)
        api_keys = [legacy] if legacy else []

    if not api_keys:
        raise ValueError("Meteonomiqs: No API keys configured")

    latitude = entry.data.get(CONF_LATITUDE)
    longitude = entry.data.get(CONF_LONGITUDE)
    language = entry.data.get(CONF_LANGUAGE, "en")

    # Create coordinator
    coordinator = MeteonomiqsDataUpdateCoordinator(
        hass,
        api_keys,
        latitude,
        longitude,
        language,
    )

    # Initial refresh (uses cache if valid)
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("MY_WEATHER: First refresh finished")

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }

    # -------------------------------------------------
    # Register manual update service (ONLY ONCE)
    # -------------------------------------------------
    if not hass.services.has_service(DOMAIN, "update"):

        async def handle_manual_update(call: ServiceCall):
            # Optional: support future multi-entry updates
            for data in hass.data.get(DOMAIN, {}).values():
                coord = data.get("coordinator")
                if coord:
                    await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN,
            "update",
            handle_manual_update,
        )

        _LOGGER.debug("MY_WEATHER: Service my_weather.update registered")

    # Forward platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug("MY_WEATHER: async_setup_entry END — Platforms forwarded")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.debug("MY_WEATHER: async_unload_entry for %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Remove service if this was the last entry
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "update")
            _LOGGER.debug("MY_WEATHER: Service my_weather.update removed")

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries to the new api_keys list format."""
    _LOGGER.debug("MY_WEATHER: Migrating config entry from v%s", entry.version)

    if entry.version < 3:
        data = dict(entry.data)

        # Legacy: single api_key -> api_keys list
        if CONF_API_KEYS not in data:
            legacy = data.get(CONF_API_KEY)
            if legacy:
                # allow comma/newline separated too
                raw = str(legacy)
                parts = []
                for chunk in raw.replace(";", ",").splitlines():
                    parts.extend([p.strip() for p in chunk.split(",")])
                keys = [p for p in parts if p]
                # de-duplicate preserve order, max 4
                seen = set()
                out = []
                for k in keys:
                    if k not in seen:
                        seen.add(k)
                        out.append(k)
                data[CONF_API_KEYS] = out[:4]
            else:
                data[CONF_API_KEYS] = []

        # Keep CONF_API_KEY for backwards compatibility? Remove to avoid confusion.
        data.pop(CONF_API_KEY, None)

        hass.config_entries.async_update_entry(entry, data=data, version=3)
        _LOGGER.info("MY_WEATHER: Migration to v3 successful")

    return True
