"""Config flow for FTP Browser integration."""
from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol
import aioftp
import async_timeout

from .const import (
    DOMAIN,
    CONF_FTP_SERVER,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_SCAN_INTERVAL
)

class FTPBrowserConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FTP Browser."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Test FTP connection
            try:
                async with async_timeout.timeout(15):
                    client = aioftp.Client()
                    await client.connect(
                        user_input[CONF_FTP_SERVER],
                        user_input.get(CONF_PORT, DEFAULT_PORT),
                        ssl=user_input.get(CONF_SSL, DEFAULT_SSL)
                    )
                    await client.login(
                        user_input[CONF_USERNAME],
                        user_input[CONF_PASSWORD]
                    )
                    # Test successful, close connection
                    await client.quit()
                
                # Check if already configured
                await self.async_set_unique_id(f"{user_input[CONF_FTP_SERVER]}_{user_input[CONF_USERNAME]}")
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"FTP: {user_input[CONF_FTP_SERVER]}",
                    data=user_input
                )
            except aioftp.errors.StatusCodeError as e:
                if "530" in str(e):  # Authentication failed
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        # Show form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FTP_SERVER): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Optional(CONF_SSL, default=DEFAULT_SSL): bool,
                    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
                }
            ),
            errors=errors,
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return FTPBrowserOptionsFlow(config_entry)

class FTPBrowserOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): int,
                    vol.Optional(
                        CONF_SSL,
                        default=self.config_entry.options.get(
                            CONF_SSL, self.config_entry.data.get(CONF_SSL, DEFAULT_SSL)
                        ),
                    ): bool,
                }
            )
        )
