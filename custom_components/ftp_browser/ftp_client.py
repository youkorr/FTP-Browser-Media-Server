"""Direct FTP client implementation using socket."""
import socket
import logging
import time
import re
import os
from typing import Tuple, Optional, List, Dict, Any, Iterator

_LOGGER = logging.getLogger(__name__)

class FTPClient:
    """Direct FTP client implementation."""

    def __init__(self, host: str, port: int = 21, timeout: int = 15):
        """Initialize the FTP client."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self.control_socket = None
        self.data_socket = None
        self.encoding = 'utf-8'
        self.passive_mode = True

    def connect(self) -> bool:
        """Connect to the FTP server."""
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(self.timeout)
            self.control_socket.connect((self.host, self.port))
            
            # Read welcome message
            response = self._read_response()
            if not response.startswith('220'):
                _LOGGER.error("FTP welcome message not received: %s", response)
                self.close()
                return False
            
            return True
            
        except Exception as e:
            _LOGGER.error("FTP connection error: %s", str(e))
            self.close()
            return False

    def login(self, username: str, password: str) -> bool:
        """Login to the FTP server."""
        try:
            # Send username
            self._send_command(f"USER {username}")
            response = self._read_response()
            if not (response.startswith('230') or response.startswith('331')):
                _LOGGER.error("FTP username failed: %s", response)
                return False
            
            # Send password if needed
            if response.startswith('331'):
                self._send_command(f"PASS {password}")
                response = self._read_response()
                if not response.startswith('230'):
                    _LOGGER.error("FTP password failed: %s", response)
                    return False
            
            # Set binary mode
            self._send_command("TYPE I")
            response = self._read_response()
            if not response.startswith('200'):
                _LOGGER.error("Failed to set binary mode: %s", response)
                return False
                
            return True
            
        except Exception as e:
            _LOGGER.error("FTP login error: %s", str(e))
            return False

    def list_directory(self, path: str = '/') -> List[Dict[str, Any]]:
        """List directory contents."""
        try:
            if path != '/':
                self._send_command(f"CWD {path}")
                response = self._read_response()
                if not response.startswith('250'):
                    _LOGGER.error("Failed to change directory: %s", response)
                    return []
            
            # Enter passive mode
            data_socket, _ = self._enter_passive_mode()
            if not data_socket:
                return []
            
            # Send LIST command
            self._send_command("LIST")
            response = self._read_response()
            if not (response.startswith('150') or response.startswith('125')):
                _LOGGER.error("Failed to list directory: %s", response)
                data_socket.close()
                return []
            
            # Read directory listing
            listing_data = b''
            while True:
                chunk = data_socket.recv(1024)
                if not chunk:
                    break
                listing_data += chunk
            
            data_socket.close()
            
            # Wait for transfer complete message
            response = self._read_response()
            if not response.startswith('226'):
                _LOGGER.warning("Transfer completion message not received: %s", response)
            
            # Parse directory listing
            files = []
            for line in listing_data.decode(self.encoding).splitlines():
                if not line.strip():
                    continue
                    
                try:
                    parts = line.split()
                    if len(parts) < 9:
                        continue
                        
                    perms = parts[0]
                    size = int(parts[4])
                    filename = ' '.join(parts[8:])
                    
                    # Skip . and ..
                    if filename in ('.', '..'):
                        continue
                        
                    is_dir = perms.startswith('d')
                    
                    file_path = os.path.join(path, filename)
                    if path == '/':
                        file_path = '/' + filename
                    
                    files.append({
                        'name': filename,
                        'path': file_path,
                        'type': 'directory' if is_dir else 'file',
                        'size': size,
                        'permissions': perms
                    })
                except Exception as e:
                    _LOGGER.warning("Error parsing FTP list item '%s': %s", line, e)
            
            return files
            
        except Exception as e:
            _LOGGER.error("Error listing directory: %s", str(e))
            return []
    
    def download_file(self, path: str) -> Iterator[bytes]:
        """Download a file and yield chunks."""
        try:
            # Enter passive mode
            data_socket, _ = self._enter_passive_mode()
            if not data_socket:
                return
            
            # Send RETR command
            self._send_command(f"RETR {path}")
            response = self._read_response()
            if not response.startswith('150'):
                _LOGGER.error("Failed to retrieve file: %s", response)
                data_socket.close()
                return
            
            # Read and yield file data in chunks
            while True:
                chunk = data_socket.recv(8192)  # 8KB chunks
                if not chunk:
                    break
                yield chunk
            
            data_socket.close()
            
            # Wait for transfer complete message
            response = self._read_response()
            if not response.startswith('226'):
                _LOGGER.warning("Transfer completion message not received: %s", response)
            
        except Exception as e:
            _LOGGER.error("Error downloading file: %s", str(e))
    
    def get_file_size(self, path: str) -> Optional[int]:
        """Get file size using SIZE command (if supported)."""
        try:
            self._send_command(f"SIZE {path}")
            response = self._read_response()
            if response.startswith('213'):
                size_str = response[4:].strip()
                return int(size_str)
            return None
        except Exception:
            return None
    
    def _enter_passive_mode(self) -> Tuple[Optional[socket.socket], Optional[Tuple[str, int]]]:
        """Enter passive mode and return data socket."""
        try:
            self._send_command("PASV")
            response = self._read_response()
            if not response.startswith('227'):
                _LOGGER.error("Failed to enter passive mode: %s", response)
                return None, None
            
            # Parse passive mode response for IP and port
            match = re.search(r'(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)', response)
            if not match:
                _LOGGER.error("Failed to parse passive mode response: %s", response)
                return None, None
                
            ip_parts = match.groups()[:4]
            port_parts = match.groups()[4:]
            
            ip = '.'.join(ip_parts)
            port = (int(port_parts[0]) << 8) + int(port_parts[1])
            
            # Create data socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((ip, port))
            
            return s, (ip, port)
            
        except Exception as e:
            _LOGGER.error("Error entering passive mode: %s", str(e))
            return None, None

    def _send_command(self, command: str) -> None:
        """Send a command to the FTP server."""
        if not self.control_socket:
            raise ConnectionError("Not connected to FTP server")
            
        cmd_bytes = (command + '\r\n').encode(self.encoding)
        self.control_socket.sendall(cmd_bytes)

    def _read_response(self) -> str:
        """Read a response from the FTP server."""
        if not self.control_socket:
            raise ConnectionError("Not connected to FTP server")
            
        response_lines = []
        
        while True:
            line = b''
            while not line.endswith(b'\r\n'):
                chunk = self.control_socket.recv(1)
                if not chunk:
                    break
                line += chunk
            
            line_str = line.decode(self.encoding).strip()
            response_lines.append(line_str)
            
            # Check if multi-line response is complete
            if line_str[:3].isdigit() and line_str[3:4] == ' ':
                break
        
        return '\n'.join(response_lines)

    def close(self) -> None:
        """Close the connection."""
        try:
            if self.control_socket:
                try:
                    # Send QUIT command
                    self._send_command("QUIT")
                    self._read_response()
                except Exception:
                    pass
                finally:
                    self.control_socket.close()
                    self.control_socket = None
        except Exception as e:
            _LOGGER.error("Error closing FTP connection: %s", str(e))
