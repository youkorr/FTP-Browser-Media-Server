"""Config flow for FTP Browser integration."""
from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol
import asyncio
import socket

from .const import (
    DOMAIN,
    CONF_FTP_SERVER,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_SCAN_INTERVAL,
    CONF_ROOT_PATH,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ROOT_PATH
)

from .ftp_client import FTPClient

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
                # Use our direct FTP client
                client = FTPClient(
                    user_input[CONF_FTP_SERVER],
                    user_input.get(CONF_PORT, DEFAULT_PORT),
                    timeout=15
                )
                
                if client.connect() and client.login(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD]
                ):
                    # Check if we can access the root path
                    root_path = user_input.get(CONF_ROOT_PATH, DEFAULT_ROOT_PATH)
                    if root_path and root_path != "/":
                        try:
                            # Try to change to root directory to verify it exists
                            client._send_command(f"CWD {root_path}")
                            response = client._read_response()
                            if not response.startswith("250"):
                                errors["root_path"] = "invalid_path"
                        except Exception:
                            errors["root_path"] = "invalid_path"
                    
                    if not errors:
                        # Close connection if successful
                        client.close()
                        
                        # Check if already configured
                        await self.async_set_unique_id(
                            f"{user_input[CONF_FTP_SERVER]}_{user_input[CONF_USERNAME]}"
                        )
                        self._abort_if_unique_id_configured()
                        
                        return self.async_create_entry(
                            title=f"FTP: {user_input[CONF_FTP_SERVER]}",
                            data=user_input
                        )
                else:
                    errors["base"] = "invalid_auth"
                
                # Make sure to close the connection
                client.close()
                    
            except socket.gaierror:
                errors["base"] = "cannot_connect"
            except ConnectionError:
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
                    vol.Optional(CONF_ROOT_PATH, default=DEFAULT_ROOT_PATH): str,
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
            # Validate root path if changed
            if (CONF_ROOT_PATH in user_input and 
                user_input[CONF_ROOT_PATH] != self.config_entry.options.get(
                    CONF_ROOT_PATH, self.config_entry.data.get(CONF_ROOT_PATH, DEFAULT_ROOT_PATH)
                )):
                
                # Test if the new root path is valid
                try:
                    client = FTPClient(
                        self.config_entry.data[CONF_FTP_SERVER],
                        self.config_entry.data.get(CONF_PORT, DEFAULT_PORT),
                        timeout=15
                    )
                    
                    if client.connect() and client.login(
                        self.config_entry.data[CONF_USERNAME],
                        self.config_entry.data[CONF_PASSWORD]
                    ):
                        if user_input[CONF_ROOT_PATH] and user_input[CONF_ROOT_PATH] != "/":
                            client._send_command(f"CWD {user_input[CONF_ROOT_PATH]}")
                            response = client._read_response()
                            if not response.startswith("250"):
                                return self.async_show_form(
                                    step_id="init",
                                    data_schema=self._get_schema(),
                                    errors={"root_path": "invalid_path"},
                                )
                        
                        client.close()
                    else:
                        client.close()
                        return self.async_show_form(
                            step_id="init",
                            data_schema=self._get_schema(),
                            errors={"base": "invalid_auth"},
                        )
                        
                except Exception:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=self._get_schema(),
                        errors={"base": "cannot_connect"},
                    )
            
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self._get_schema(),
        )
    
    def _get_schema(self):
        """Get the schema for the options form."""
        return vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, 
                        self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ),
                ): int,
                vol.Optional(
                    CONF_SSL,
                    default=self.config_entry.options.get(
                        CONF_SSL, 
                        self.config_entry.data.get(CONF_SSL, DEFAULT_SSL)
                    ),
                ): bool,
                vol.Optional(
                    CONF_ROOT_PATH,
                    default=self.config_entry.options.get(
                        CONF_ROOT_PATH, 
                        self.config_entry.data.get(CONF_ROOT_PATH, DEFAULT_ROOT_PATH)
                    ),
                ): str,
            }
        )

