"""The Card Installer integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, Event
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .card_manager import CardManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Card Installer from a config entry."""
    _LOGGER.info("Setting up Card Installer integration")

    # Get configuration
    repo_url = entry.data.get("repo_url")
    branch = entry.data.get("branch", "master")
    auto_update = entry.data.get("auto_update", True)
    update_interval = entry.data.get("update_interval", 3600)

    if not repo_url:
        _LOGGER.error("Repository URL is required")
        return False

    # Initialize card manager
    card_manager = CardManager(hass, repo_url, branch, auto_update, update_interval)

    # Store card manager in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = card_manager

    # Register services (only once for all entries)
    if DOMAIN not in hass.data or "services_registered" not in hass.data[DOMAIN]:
        await _async_register_services(hass)
        hass.data[DOMAIN]["services_registered"] = True

    # Install cards automatically after Home Assistant starts
    # This ensures startup is not blocked by downloads
    async def install_cards_after_startup(event: Event | None) -> None:
        """Install cards after Home Assistant has fully started."""
        # Wait a bit more to ensure everything is ready
        await asyncio.sleep(5)
        try:
            _LOGGER.info("Starting automatic card installation from %s", repo_url)
            await card_manager.async_install_cards()
            _LOGGER.info("Automatic card installation completed")
        except asyncio.CancelledError:
            _LOGGER.info("Card installation task was cancelled")
        except Exception as err:
            _LOGGER.error("Error during automatic card installation: %s", err, exc_info=True)

    # Listen for Home Assistant started event to install cards
    # This ensures we don't block startup
    if hass.is_running:
        # If already running, start immediately
        hass.async_create_task(install_cards_after_startup(None))
    else:
        # Otherwise, wait for startup event
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, install_cards_after_startup)

    # Start auto-update task if enabled
    if auto_update:
        card_manager.start_auto_update()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.
    
    Note: This does NOT delete downloaded card files. Files remain in
    www/community/ directory and resources remain in Lovelace resources.
    This allows you to uninstall the integration without losing your cards.
    """
    _LOGGER.info("Unloading Card Installer integration")

    # Stop auto-update task
    entry_id = entry.entry_id
    if entry_id in hass.data.get(DOMAIN, {}):
        card_manager = hass.data[DOMAIN][entry_id]
        card_manager.stop_auto_update()

    # Remove from hass data
    # Note: We intentionally do NOT delete downloaded files or resources
    # Files in www/community/ and resources in Lovelace will remain
    hass.data[DOMAIN].pop(entry_id, None)

    _LOGGER.info("Card Installer unloaded. Downloaded files and resources are preserved.")
    return True


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register services for the integration."""

    async def install_cards_service(call) -> None:
        """Service to install cards from repository."""
        _LOGGER.info("Service call: install_cards")
        
        # Get entry_id from service call if provided, otherwise use first entry
        entry_id = call.data.get("entry_id")
        
        if entry_id and entry_id in hass.data.get(DOMAIN, {}):
            card_manager = hass.data[DOMAIN][entry_id]
        else:
            # Use first available entry
            entries = {k: v for k, v in hass.data.get(DOMAIN, {}).items() if isinstance(v, CardManager)}
            if not entries:
                _LOGGER.error("No Card Installer entries found")
                return
            card_manager = list(entries.values())[0]
        
        try:
            await card_manager.async_install_cards()
        except Exception as err:
            _LOGGER.error("Error installing cards: %s", err)
            raise

    async def update_cards_service(call) -> None:
        """Service to update cards from repository."""
        _LOGGER.info("Service call: update_cards")
        
        # Get entry_id from service call if provided, otherwise use first entry
        entry_id = call.data.get("entry_id")
        
        if entry_id and entry_id in hass.data.get(DOMAIN, {}):
            card_manager = hass.data[DOMAIN][entry_id]
        else:
            # Use first available entry
            entries = {k: v for k, v in hass.data.get(DOMAIN, {}).items() if isinstance(v, CardManager)}
            if not entries:
                _LOGGER.error("No Card Installer entries found")
                return
            card_manager = list(entries.values())[0]
        
        try:
            await card_manager.async_update_cards()
        except Exception as err:
            _LOGGER.error("Error updating cards: %s", err)
            raise

    async def remove_card_service(call) -> None:
        """Service to remove a specific card."""
        url = call.data.get("url")
        filename = call.data.get("filename")

        if not url and not filename:
            _LOGGER.error("Either 'url' or 'filename' must be provided")
            return

        _LOGGER.info("Service call: remove_card - url: %s, filename: %s", url, filename)
        
        # Get entry_id from service call if provided, otherwise use first entry
        entry_id = call.data.get("entry_id")
        
        if entry_id and entry_id in hass.data.get(DOMAIN, {}):
            card_manager = hass.data[DOMAIN][entry_id]
        else:
            # Use first available entry
            entries = {k: v for k, v in hass.data.get(DOMAIN, {}).items() if isinstance(v, CardManager)}
            if not entries:
                _LOGGER.error("No Card Installer entries found")
                return
            card_manager = list(entries.values())[0]
        
        try:
            await card_manager.async_remove_card(url, filename)
        except Exception as err:
            _LOGGER.error("Error removing card: %s", err)
            raise

    async def add_local_cards_to_resources_service(call) -> None:
        """Service to add local card files to Lovelace resources."""
        _LOGGER.info("Service call: add_local_cards_to_resources")
        
        # Get entry_id from service call if provided, otherwise use first entry
        entry_id = call.data.get("entry_id")
        
        if entry_id and entry_id in hass.data.get(DOMAIN, {}):
            card_manager = hass.data[DOMAIN][entry_id]
        else:
            # Use first available entry
            entries = {k: v for k, v in hass.data.get(DOMAIN, {}).items() if isinstance(v, CardManager)}
            if not entries:
                _LOGGER.error("No Card Installer entries found")
                return
            card_manager = list(entries.values())[0]
        
        try:
            await card_manager.async_add_local_cards_to_resources()
        except Exception as err:
            _LOGGER.error("Error adding local cards to resources: %s", err)
            raise

    # Register services
    hass.services.async_register(DOMAIN, "install_cards", install_cards_service)
    hass.services.async_register(DOMAIN, "update_cards", update_cards_service)
    hass.services.async_register(DOMAIN, "remove_card", remove_card_service)
    hass.services.async_register(DOMAIN, "add_local_cards_to_resources", add_local_cards_to_resources_service)

