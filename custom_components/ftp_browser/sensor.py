"""Sensor platform for FTP Browser."""
from homeassistant.components.sensor import SensorEntity
import logging
import aioftp
import async_timeout
from datetime import timedelta

from .const import DOMAIN, CONF_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up FTP file count sensor from config entry."""
    entry_data = hass.data[DOMAIN]["entries"][entry.entry_id]
    
    sensor = FTPFilesCountSensor(hass, entry, entry_data)
    async_add_entities([sensor], True)

class FTPFilesCountSensor(SensorEntity):
    """Sensor showing the number of files on the FTP server."""
    
    def __init__(self, hass, entry, entry_data):
        """Initialize the sensor."""
        self.hass = hass
        self.entry = entry
        self.entry_id = entry.entry_id
        self.entry_data = entry_data
        self._attr_unique_id = f"{entry.entry_id}_file_count"
        self._attr_name = f"FTP {entry_data['server']} Files"
        self._attr_native_unit_of_measurement = "files"
        self._attr_icon = "mdi:file-multiple"
        self._attr_extra_state_attributes = {
            "server": entry_data["server"],
            "last_update": None,
            "file_count": 0,
            "dir_count": 0,
            "total_size": 0
        }
        self._state = None
    
    @property
    def available(self):
        """Return True if entity is available."""
        return self._state is not None
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state
    
    async def async_update(self):
        """Update the sensor state."""
        try:
            # Create a new connection for each update
            async with async_timeout.timeout(30):
                client = aioftp.Client()
                await client.connect(
                    self.entry_data["server"],
                    self.entry_data["port"],
                    ssl=self.entry_data["ssl"]
                )
                await client.login(
                    self.entry_data["username"],
                    self.entry_data["password"]
                )
                
                # Count files in root directory
                file_count = 0
                dir_count = 0
                total_size = 0
                
                async for info in client.list():
                    if info["type"] == "dir":
                        dir_count += 1
                    else:
                        file_count += 1
                        total_size += info.get("size", 0)
                
                # Update state and attributes
                self._state = file_count
                self._attr_extra_state_attributes.update({
                    "last_update": self.hass.states.get(self.entity_id).last_updated,
                    "file_count": file_count,
                    "dir_count": dir_count,
                    "total_size": total_size,
                    "total_size_readable": self._format_size(total_size)
                })
                
                await client.quit()
                
        except Exception as e:
            _LOGGER.error(f"Error updating FTP sensor: {e}")
            # Don't update state on error
    
    def _format_size(self, size_bytes):
        """Format size in bytes to human readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
