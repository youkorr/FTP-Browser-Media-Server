"""FTP Browser & Media Server integration for Home Assistant."""
import os
import logging
import json
import time
import voluptuous as vol
import aioftp
import asyncio
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta
from homeassistant.components.http import HomeAssistantView
from aiohttp import web

from .const import (
    DOMAIN, 
    CONF_FTP_SERVER, 
    CONF_USERNAME, 
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    SERVICE_CREATE_SHARE,
    SERVICE_DELETE_SHARE,
    STORAGE_KEY,
    STORAGE_VERSION
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "media_source"]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the FTP Browser component."""
    hass.data.setdefault(DOMAIN, {
        "shared_links": {},
        "entries": {}
    })
    
    # Initialize storage for shared links
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load()
    
    if stored_data:
        # Validate and clean up expired links
        now = time.time()
        valid_links = {}
        for link_id, link_data in stored_data.get("shared_links", {}).items():
            if link_data.get("expiry", 0) > now:
                valid_links[link_id] = link_data
        
        hass.data[DOMAIN]["shared_links"] = valid_links
        await store.async_save({"shared_links": valid_links})
        _LOGGER.info(f"Loaded {len(valid_links)} valid shared links")
    
    # Register API endpoints
    hass.http.register_view(FTPListView)
    hass.http.register_view(FTPDownloadView)
    hass.http.register_view(FTPShareView)
    
    # Register services
    async def create_share_link(call):
        """Service to create a share link."""
        entry_id = call.data.get("entry_id")
        path = call.data.get("path")
        duration = call.data.get("duration", 24)  # hours
        
        if not entry_id or not path:
            _LOGGER.error("Missing required fields: entry_id and path")
            return
            
        if entry_id not in hass.data[DOMAIN]["entries"]:
            _LOGGER.error(f"Unknown config entry: {entry_id}")
            return
            
        entry_data = hass.data[DOMAIN]["entries"][entry_id]
        
        # Generate a unique token
        import uuid
        token = str(uuid.uuid4())
        
        # Store the link
        expiry = time.time() + (duration * 3600)
        hass.data[DOMAIN]["shared_links"][token] = {
            "entry_id": entry_id,
            "path": path,
            "expiry": expiry,
            "created": time.time()
        }
        
        # Save to persistent storage
        await store.async_save({"shared_links": hass.data[DOMAIN]["shared_links"]})
        
        # Notify the user with the link
        base_url = hass.config.api.base_url
        share_url = f"{base_url}/api/ftp_browser/download/{token}"
        
        _LOGGER.info(f"Created share link: {share_url}, expires in {duration} hours")
        return {"url": share_url, "token": token, "expiry": expiry}
    
    async def delete_share_link(call):
        """Service to delete a share link."""
        token = call.data.get("token")
        
        if not token:
            _LOGGER.error("Missing required field: token")
            return
            
        if token in hass.data[DOMAIN]["shared_links"]:
            del hass.data[DOMAIN]["shared_links"][token]
            await store.async_save({"shared_links": hass.data[DOMAIN]["shared_links"]})
            _LOGGER.info(f"Deleted share link with token: {token}")
            return {"success": True}
        else:
            _LOGGER.warning(f"Share link with token {token} not found")
            return {"success": False, "error": "Token not found"}
    
    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_SHARE, create_share_link,
        vol.Schema({
            vol.Required("entry_id"): str,
            vol.Required("path"): str,
            vol.Optional("duration"): int,
        })
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_SHARE, delete_share_link,
        vol.Schema({
            vol.Required("token"): str,
        })
    )
    
    async def clean_expired_shares(now=None):
        """Clean up expired share links."""
        current_time = time.time()
        shared_links = hass.data[DOMAIN]["shared_links"]
        expired = []
        
        for token, link_data in shared_links.items():
            if link_data.get("expiry", 0) < current_time:
                expired.append(token)
        
        if expired:
            for token in expired:
                del shared_links[token]
            await store.async_save({"shared_links": shared_links})
            _LOGGER.info(f"Cleaned up {len(expired)} expired share links")
    
    # Schedule periodic cleanup of expired shares
    async_track_time_interval(
        hass, clean_expired_shares, timedelta(hours=1)
    )
    
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up FTP Browser from a config entry."""
    hass.data[DOMAIN]["entries"][entry.entry_id] = {
        "server": entry.data[CONF_FTP_SERVER],
        "username": entry.data[CONF_USERNAME],
        "password": entry.data[CONF_PASSWORD],
        "port": entry.data.get(CONF_PORT, 21),
        "ssl": entry.data.get(CONF_SSL, False),
        "scan_interval": entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        "client": None
    }
    
    # Create a connection to test and cache
    try:
        client = aioftp.Client()
        await client.connect(
            entry.data[CONF_FTP_SERVER],
            entry.data.get(CONF_PORT, 21),
            ssl=entry.data.get(CONF_SSL, False)
        )
        await client.login(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD]
        )
        
        hass.data[DOMAIN]["entries"][entry.entry_id]["client"] = client
        _LOGGER.info(f"Successfully connected to FTP server: {entry.data[CONF_FTP_SERVER]}")
    except Exception as e:
        _LOGGER.error(f"Failed to connect to FTP server: {e}")
        # Don't keep the client in a broken state
        hass.data[DOMAIN]["entries"][entry.entry_id]["client"] = None
        # Connection failed, but we'll still set up the platforms and retry later
    
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )
        
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Close FTP connection if open
    client = hass.data[DOMAIN]["entries"].get(entry.entry_id, {}).get("client")
    if client:
        try:
            await client.quit()
        except Exception as e:
            _LOGGER.warning(f"Error closing FTP connection: {e}")
    
    # Unload platforms
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    
    if unload_ok:
        hass.data[DOMAIN]["entries"].pop(entry.entry_id)
        
    return unload_ok

class FTPListView(HomeAssistantView):
    """View to handle FTP directory listing requests."""
    url = "/api/ftp_browser/list/{entry_id}"
    name = "api:ftp_browser:list"
    
    async def get(self, request, entry_id):
        """Handle GET request for FTP directory listing."""
        hass = request.app["hass"]
        
        if entry_id not in hass.data[DOMAIN]["entries"]:
            return self.json_message(f"Config entry {entry_id} not found", 404)
        
        entry_data = hass.data[DOMAIN]["entries"][entry_id]
        path = request.query.get("path", "/")
        
        # Create or reuse FTP client
        client = entry_data.get("client")
        need_to_connect = True
        
        if client:
            try:
                # Test if connection is still active
                await client.command("NOOP")
                need_to_connect = False
            except Exception:
                # Connection lost, reconnect
                try:
                    await client.quit()
                except Exception:
                    pass
                client = None
        
        if need_to_connect:
            try:
                client = aioftp.Client()
                await client.connect(
                    entry_data["server"],
                    entry_data["port"],
                    ssl=entry_data["ssl"]
                )
                await client.login(
                    entry_data["username"],
                    entry_data["password"]
                )
                entry_data["client"] = client
            except Exception as e:
                return self.json_message(f"Failed to connect to FTP server: {str(e)}", 502)
        
        try:
            # Navigate to the requested path
            if path != '/':
                await client.change_directory(path)
            
            # List files and directories
            file_list = []
            async for info in client.list():
                is_dir = info["type"] == "dir"
                file_path = f"{path}/{info['name']}" if path == '/' else f"{path}/{info['name']}"
                file_path = file_path.replace('//', '/')
                
                file_info = {
                    "name": info["name"],
                    "path": file_path,
                    "type": "directory" if is_dir else "file",
                    "size": info.get("size", 0),
                    "modified": info.get("modify", None)
                }
                
                # For directories, add a trailing slash for clarity
                if is_dir and not file_path.endswith("/"):
                    file_info["path"] = f"{file_path}/"
                
                file_list.append(file_info)
            
            # Sort: directories first, then files, all alphabetically
            file_list.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
            
            return self.json(file_list)
        except Exception as e:
            _LOGGER.error(f"Error listing FTP directory: {e}")
            return self.json_message(f"Error listing directory: {str(e)}", 500)

class FTPDownloadView(HomeAssistantView):
    """View to handle FTP file download requests."""
    url = "/api/ftp_browser/download/{token}"
    name = "api:ftp_browser:download"
    requires_auth = False  # Public access with token
    cors_allowed = True
    
    async def get(self, request, token):
        """Handle GET request for FTP file download."""
        hass = request.app["hass"]
        
        # Verify the token
        shared_links = hass.data[DOMAIN]["shared_links"]
        if token not in shared_links:
            return self.json_message("Invalid download token", 404)
        
        link_data = shared_links[token]
        
        # Check if expired
        if link_data.get("expiry", 0) < time.time():
            return self.json_message("Download link has expired", 410)
        
        entry_id = link_data["entry_id"]
        path = link_data["path"]
        
        if entry_id not in hass.data[DOMAIN]["entries"]:
            return self.json_message("Server configuration not found", 500)
        
        entry_data = hass.data[DOMAIN]["entries"][entry_id]
        
        # Create a new FTP connection for downloading
        # It's better to use a separate connection for downloads to not interfere with browsing
        try:
            client = aioftp.Client()
            await client.connect(
                entry_data["server"],
                entry_data["port"],
                ssl=entry_data["ssl"]
            )
            await client.login(
                entry_data["username"],
                entry_data["password"]
            )
        except Exception as e:
            _LOGGER.error(f"Failed to connect to FTP server for download: {e}")
            return self.json_message(f"Server connection error: {str(e)}", 502)
        
        try:
            # Get file info
            file_name = os.path.basename(path)
            
            # Determine mime type
            content_type = self._guess_mime_type(file_name)
            
            # Set up streaming response
            response = web.StreamResponse()
            response.headers["Content-Type"] = content_type
            response.headers["Content-Disposition"] = f'attachment; filename="{file_name}"'
            
            # Start streaming response
            await response.prepare(request)
            
            # Get file size if possible
            try:
                file_size = await self._get_file_size(client, path)
                if file_size:
                    response.headers["Content-Length"] = str(file_size)
            except Exception as e:
                _LOGGER.warning(f"Could not determine file size: {e}")
            
            # Download and stream the file
            stream = await client.download_stream(path)
            
            async for chunk in stream.iter_by_block(8192):
                await response.write(chunk)
            
            await response.write_eof()
            await client.quit()
            
            return response
            
        except Exception as e:
            _LOGGER.error(f"Error downloading file: {e}")
            try:
                await client.quit()
            except Exception:
                pass
            return self.json_message(f"Error downloading file: {str(e)}", 500)
    
    def _guess_mime_type(self, filename):
        """Guess the MIME type based on file extension."""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"
    
    async def _get_file_size(self, client, path):
        """Get the file size if possible."""
        dir_path = os.path.dirname(path)
        file_name = os.path.basename(path)
        
        if dir_path:
            await client.change_directory(dir_path)
        
        async for info in client.list():
            if info["name"] == file_name:
                return info.get("size")
        
        return None

class FTPShareView(HomeAssistantView):
    """View to handle FTP share link creation."""
    url = "/api/ftp_browser/share"
    name = "api:ftp_browser:share"
    
    async def post(self, request):
        """Handle POST request to create share link."""
        hass = request.app["hass"]
        try:
            data = await request.json()
        except ValueError:
            return self.json_message("Invalid JSON", 400)
        
        entry_id = data.get("entry_id")
        path = data.get("path")
        duration = data.get("duration", 24)  # hours
        
        if not entry_id or not path:
            return self.json_message("Missing required fields: entry_id and path", 400)
            
        if entry_id not in hass.data[DOMAIN]["entries"]:
            return self.json_message(f"Unknown config entry: {entry_id}", 404)
        
        # Generate a unique token
        import uuid
        token = str(uuid.uuid4())
        
        # Store the link
        expiry = time.time() + (duration * 3600)
        hass.data[DOMAIN]["shared_links"][token] = {
            "entry_id": entry_id,
            "path": path,
            "expiry": expiry,
            "created": time.time()
        }
        
        # Save to persistent storage
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        await store.async_save({"shared_links": hass.data[DOMAIN]["shared_links"]})
        
        # Return the share URL
        base_url = hass.config.api.base_url
        share_url = f"{base_url}/api/ftp_browser/download/{token}"
        
        return self.json({
            "url": share_url,
            "token": token,
            "expiry": expiry,
            "expiry_human": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry))
        })

