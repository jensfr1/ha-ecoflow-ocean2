"""Einrichtung ueber die Benutzeroberflaeche."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import EcoflowAuthError, EcoflowConnectionError, async_validate_credentials
from .const import CONF_DEVICE_SN, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_DEVICE_SN): str,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class EcoflowOcean2ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Fuehrt durch die Einrichtung."""

    VERSION = 1

    async def _async_check(self, email: str, password: str) -> str | None:
        """Prueft die Zugangsdaten; gibt einen Fehlerschluessel zurueck oder None.

        Der Test laeuft bereits im Dialog - so faellt ein Tippfehler sofort auf,
        statt erst spaeter als rote Integration.
        """
        session = async_get_clientsession(self.hass)
        try:
            await async_validate_credentials(session, email, password)
        except EcoflowAuthError:
            return "invalid_auth"
        except EcoflowConnectionError:
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error while validating credentials")
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Erster Schritt: Zugangsdaten und Seriennummer."""
        errors: dict[str, str] = {}

        if user_input is not None:
            serial = user_input[CONF_DEVICE_SN].strip().upper()
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()

            error = await self._async_check(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"PowerOcean {serial}",
                    data={**user_input, CONF_DEVICE_SN: serial},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Wird ausgeloest, wenn EcoFlow die Zugangsdaten ablehnt."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fragt das Passwort erneut ab."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            error = await self._async_check(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
