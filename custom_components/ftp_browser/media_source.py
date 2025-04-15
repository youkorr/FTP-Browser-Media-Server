"""Media Source implementation for FTP Browser."""
from homeassistant.components.media_player.const import (
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_IMAGE,
    MEDIA_CLASS_VIDEO,
    MEDIA_CLASS_MUSIC,
    MEDIA_TYPE_MUSIC,
    MEDIA_TYPE_VIDEO,
    MEDIA_TYPE_IMAGE,
)
from homeassistant.components.media_source import (
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    BrowseMedia,
    MEDIA_CLASS_APP,
    MEDIA_MIME_TYPES,
)
import aioftp
import os
import logging
import mimetypes
import urllib.parse
import async_timeout

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_get_media_source(hass):
    """Get FTP media source."""
    return FTPMediaSource(hass)

class FTPMediaSource(MediaSource):
    """Provide FTP servers as media sources."""
    
    name = "FTP Browser"
    
    def __init__(self, hass):
        """Initialize FTP media source."""
        super().__init__(DOMAIN)
        self.hass = hass
        
    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a media item to a playable item."""
        _, entry_id, path = item.identifier.split("/", 2)
        
        if entry_id not in self.hass.data[DOMAIN]["entries"]:
            raise ValueError(f"Unknown FTP server: {entry_id}")
        
        # Create a download link that will be valid for 4 hours
        service_data = {
            "entry_id": entry_id,
            "path": path,
            "duration": 4
        }
        
        result = await self.hass.services.async_call(
            DOMAIN, 
            "create_share", 
            service_data,
            blocking=True,
            return_response=True
        )
        
        # Get mime type
        mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        
        # Return the URL for direct playback
        return PlayMedia(result["url"], mime_type)
    
    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMedia:
        """Browse media."""
        if item.identifier:
            # Browse specific entry/path
            path_parts = item.identifier.split("/")
            if len(path_parts) >= 2:
                entry_id = path_parts[1]
                # Reconstruct the path from remaining parts
                path = "/" + "/".join(path_parts[2:]) if len(path_parts) > 2 else "/"
                return await self._browse_ftp(entry_id, path)
        
        # Show list of FTP servers
        base = BrowseMedia(
            media_class=MEDIA_CLASS_APP,
            media_content_id="",
            media_content_type="",
            title="FTP Servers",
            can_play=False,
            can_expand=True,
            children_media_class=MEDIA_CLASS_APP,
            thumbnail=None,
        )
        
        # Add each FTP server as a child
        for entry_id, entry_data in self.hass.data[DOMAIN]["entries"].items():
            server = entry_data["server"]
            child = BrowseMedia(
                media_class=MEDIA_CLASS_DIRECTORY,
                media_content_id=f"{DOMAIN}/{entry_id}/",
                media_content_type="",
                title=f"FTP: {server}",
                can_play=False,
                can_expand=True,
                thumbnail=None,
            )
            base.children.append(child)
        
        return base
    
    async def _browse_ftp(self, entry_id, path):
        """Browse a specific FTP server path."""
        if entry_id not in self.hass.data[DOMAIN]["entries"]:
            raise ValueError(f"Unknown FTP server: {entry_id}")
        
        entry_data = self.hass.data[DOMAIN]["entries"][entry_id]
        
        # Get the FTP client
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
                _LOGGER.error(f"Failed to connect to FTP server: {e}")
                raise ValueError(f"Failed to connect to FTP server: {str(e)}")
        
        # Create base media item for current directory
        title = os.path.basename(path) if path != "/" else entry_data["server"]
        if not title:
            title = "Root"
            
        base = BrowseMedia(
            media_class=MEDIA_CLASS_DIRECTORY,
            media_content_id=f"{DOMAIN}/{entry_id}{path}",
            media_content_type="",
            title=title,
            can_play=False,
            can_expand=True,
            children=[],
            thumbnail=None,
        )
        
        # Add parent directory if not in root
        if path != "/":
            parent_path = os.path.dirname(path)
            if not parent_path:
                parent_path = "/"
            
            parent = BrowseMedia(
                media_class=MEDIA_CLASS_DIRECTORY,
                media_content_id=f"{DOMAIN}/{entry_id}{parent_path}",
                media_content_type="",
                title="..",
                can_play=False,
                can_expand=True,
                thumbnail=None,
            )
            base.children.append(parent)
        
        try:
            # Navigate to the requested path
            if path != '/':
                await client.change_directory(path)
            
            # List files and directories
            async for info in client.list():
                try:
                    is_dir = info["type"] == "dir"
                    name = info["name"]
                    file_path = f"{path}/{name}" if path.endswith("/") or path == "/" else f"{path}/{name}"
                    file_path = file_path.replace('//', '/')
                    
                    if is_dir:
                        child = BrowseMedia(
                            media_class=MEDIA_CLASS_DIRECTORY,
                            media_content_id=f"{DOMAIN}/{entry_id}{file_path}",
                            media_content_type="",
                            title=name,
                            can_play=False,
                            can_expand=True,
                            thumbnail=None,
                        )
                    else:
                        # Determine media class and type for files
                        mime_type, _ = mimetypes.guess_type(name)
                        media_class = MEDIA_CLASS_APP
                        media_type = ""
                        can_play = False
                        
                        if mime_type:
                            if mime_type.startswith("image/"):
                                media_class = MEDIA_CLASS_IMAGE
                                media_type = MEDIA_TYPE_IMAGE
                                can_play = True
                            elif mime_type.startswith("video/"):
                                media_class = MEDIA_CLASS_VIDEO
                                media_type = MEDIA_TYPE_VIDEO
                                can_play = True
                            elif mime_type.startswith("audio/"):
                                media_class = MEDIA_CLASS_MUSIC
                                media_type = MEDIA_TYPE_MUSIC
                                can_play = True
                        
                        child = BrowseMedia(
                            media_class=media_class,
                            media_content_id=f"{DOMAIN}/{entry_id}{file_path}",
                            media_content_type=media_type,
                            title=name,
                            can_play=can_play,
                            can_expand=False,
                            thumbnail=None,
                        )
                    
                    base.children.append(child)
                except Exception as e:
                    _LOGGER.warning(f"Error processing FTP item {info.get('name', 'unknown')}: {e}")
                    continue
            
            # Sort children: directories first, then files
            base.children.sort(
                key=lambda x: (
                    x.media_class != MEDIA_CLASS_DIRECTORY,  # Directories first
                    x.title.lower()  # Then alphabetically
                )
            )
            
            return base
            
        except Exception as e:
            _LOGGER.error(f"Error browsing FTP directory: {e}")
            raise ValueError(f"Error browsing directory: {str(e)}")
