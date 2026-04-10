"""
GPS Device Interface
====================
Interface for serial GPS devices using NMEA protocol.
Supports both real GPS devices and mock for testing.
"""

from devices.base import BaseDevice, MockGPSDevice
import serial
import pynmea2
from datetime import datetime

class GPSDevice(BaseDevice):
    """
    Real GPS device interface using serial connection.
    Parses NMEA sentences from GPS receivers.
    """
    
    def __init__(self, port='/dev/ttyUSB0', baudrate=9600, use_mock=False):
        """
        Initialize GPS device.
        
        Args:
            port: Serial port path
            baudrate: Serial baud rate
            use_mock: Use mock device if True
        """
        super().__init__(use_mock)
        
        if use_mock:
            self.device = MockGPSDevice()
        else:
            self.port = port
            self.baudrate = baudrate
            self.serial_connection = None
    
    def connect(self):
        """Establish serial connection to GPS."""
        if self.use_mock:
            return self.device.connect()
        
        try:
            self.serial_connection = serial.Serial(
                self.port,
                self.baudrate,
                timeout=1
            )
            self.connected = True
            return True
        except Exception as e:
            print(f"GPS connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Close GPS serial connection."""
        if self.use_mock:
            return self.device.disconnect()
        
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        self.connected = False
    
    def is_connected(self):
        """Check GPS connection status."""
        if self.use_mock:
            return self.device.is_connected()
        return self.connected and self.serial_connection.is_open
    
    def get_position(self):
        """
        Read and parse GPS position.
        
        Returns:
            dict: Position data or None if unavailable
        """
        if self.use_mock:
            return self.device.get_position()
        
        if not self.is_connected():
            return None
        
        try:
            # Read NMEA sentences until we get GGA (position)
            for _ in range(10):  # Try up to 10 lines
                line = self.serial_connection.readline().decode('ascii', errors='ignore')
                
                if line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                    msg = pynmea2.parse(line)
                    
                    if msg.latitude and msg.longitude:
                        # Calculate Maidenhead grid locator
                        grid = self._calculate_grid(msg.latitude, msg.longitude)
                        
                        return {
                            'latitude': msg.latitude,
                            'longitude': msg.longitude,
                            'altitude': msg.altitude,
                            'grid': grid,
                            'time': datetime.utcnow().isoformat(),
                            'satellites': msg.num_sats
                        }
            
            return None
        except Exception as e:
            print(f"GPS read error: {e}")
            return None
    
    @staticmethod
    def _calculate_grid(lat, lon):
        """
        Calculate Maidenhead grid locator from lat/lon.
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            
        Returns:
            str: 4 or 6 character grid locator (e.g., "FN20")
        """
        # Adjust coordinates
        adj_lat = lat + 90
        adj_lon = lon + 180
        
        # Calculate field (first pair)
        field_lon = chr(int(adj_lon / 20) + ord('A'))
        field_lat = chr(int(adj_lat / 10) + ord('A'))
        
        # Calculate square (second pair)
        square_lon = str(int((adj_lon % 20) / 2))
        square_lat = str(int((adj_lat % 10)))
        
        # Calculate subsquare (third pair) - optional for 6-char grid
        subsquare_lon = chr(int((adj_lon % 2) * 12) + ord('a'))
        subsquare_lat = chr(int((adj_lat % 1) * 24) + ord('a'))
        
        # Return 4-character grid (field + square)
        return f"{field_lon}{field_lat}{square_lon}{square_lat}"

# Factory function to get GPS device based on configuration
def get_gps_device(config):
    """
    Factory function to create GPS device based on configuration.
    
    Args:
        config: Flask config object
        
    Returns:
        GPSDevice: Configured GPS device instance
    """
    return GPSDevice(
        port=config.get('GPS_SERIAL_PORT', '/dev/ttyUSB0'),
        baudrate=config.get('GPS_BAUD_RATE', 9600),
        use_mock=config.get('USE_MOCK_DEVICES', True)
    )