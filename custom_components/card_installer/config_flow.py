"""Config flow for Card Installer integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_REPO_URL,
    CONF_BRANCH,
    CONF_AUTO_UPDATE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BRANCH,
    DEFAULT_AUTO_UPDATE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REPO_URL): str,
        vol.Optional(CONF_BRANCH, default=DEFAULT_BRANCH): str,
        vol.Optional(CONF_AUTO_UPDATE, default=DEFAULT_AUTO_UPDATE): bool,
        vol.Optional(
            CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
        ): vol.All(vol.Coerce(int), vol.Range(min=300)),  # Minimum 5 minutes
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Card Installer."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={
                    "repo_url": "https://gitee.com/username/repo 或 https://github.com/username/repo"
                },
            )

        errors = {}

        # Validate repository URL
        repo_url = user_input[CONF_REPO_URL]
        if not await self._validate_repo_url(repo_url):
            errors["base"] = "invalid_repo_url"

        if errors:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        # Check if already configured
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"卡片安装器 - {repo_url}",
            data=user_input,
        )

    async def _validate_repo_url(self, url: str) -> bool:
        """Validate repository URL format."""
        if not url:
            return False

        # Check if it's a valid Gitee or GitHub URL
        if url.startswith("https://gitee.com/") or url.startswith("https://github.com/"):
            # Basic validation - check if it has at least username/repo
            parts = url.replace("https://", "").replace("http://", "").split("/")
            if len(parts) >= 3:
                return True

        return False


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

