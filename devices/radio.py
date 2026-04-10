"""
Radio Control Interface
=======================
Interface for controlling radios via Hamlib.
Supports Yaesu FT-891 and other Hamlib-compatible radios.
"""

from devices.base import BaseDevice, MockRadioDevice
import subprocess
import re

class HamlibRadio(BaseDevice):
    """
    Radio control using Hamlib's rigctl command.
    
    Hamlib provides a standardized interface to many radio models.
    This class uses the rigctl command-line tool for communication.
    """
    
    def __init__(self, model=1035, port='/dev/ttyUSB1', baudrate=38400, use_mock=False):
        """
        Initialize Hamlib radio interface.
        
        Args:
            model: Hamlib radio model number (1035 = Yaesu FT-891)
            port: Serial port path
            baudrate: Serial baud rate
            use_mock: Use mock device if True
        """
        super().__init__(use_mock)
        
        if use_mock:
            self.device = MockRadioDevice()
        else:
            self.model = model
            self.port = port
            self.baudrate = baudrate
    
    def connect(self):
        """Test connection to radio via Hamlib."""
        if self.use_mock:
            return self.device.connect()
        
        try:
            # Test connection by querying frequency
            result = self._execute_command('f')
            self.connected = result is not None
            return self.connected
        except Exception as e:
            print(f"Radio connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from radio."""
        if self.use_mock:
            return self.device.disconnect()
        
        self.connected = False
    
    def is_connected(self):
        """Check radio connection status."""
        if self.use_mock:
            return self.device.is_connected()
        return self.connected
    
    def _execute_command(self, command):
        """
        Execute a Hamlib rigctl command.
        
        Args:
            command: Hamlib command string
            
        Returns:
            str: Command output or None on error
        """
        try:
            cmd = [
                'rigctl',
                '-m', str(self.model),
                '-r', self.port,
                '-s', str(self.baudrate),
                command
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            print(f"Hamlib command error: {e}")
            return None
    
    def get_frequency(self):
        """
        Get current frequency in MHz.
        
        Returns:
            float: Frequency in MHz or None
        """
        if self.use_mock:
            return self.device.get_frequency()
        
        freq_hz = self._execute_command('f')
        if freq_hz:
            try:
                return float(freq_hz) / 1_000_000  # Convert Hz to MHz
            except ValueError:
                return None
        return None
    
    def set_frequency(self, freq_mhz):
        """
        Set frequency in MHz.
        
        Args:
            freq_mhz: Frequency in MHz
            
        Returns:
            bool: True if successful
        """
        if self.use_mock:
            return self.device.set_frequency(freq_mhz)
        
        freq_hz = int(freq_mhz * 1_000_000)
        result = self._execute_command(f'F {freq_hz}')
        return result is not None
    
    def get_mode(self):
        """
        Get current operating mode.
        
        Returns:
            str: Mode (USB, LSB, CW, FM, etc.) or None
        """
        if self.use_mock:
            return self.device.get_mode()
        
        mode_info = self._execute_command('m')
        if mode_info:
            # Parse mode from output (format: "MODE\nBandwidth")
            return mode_info.split('\n')[0]
        return None
    
    def set_mode(self, mode, bandwidth=0):
        """
        Set operating mode.
        
        Args:
            mode: Mode string (USB, LSB, CW, FM, etc.)
            bandwidth: Bandwidth in Hz (0 for default)
            
        Returns:
            bool: True if successful
        """
        if self.use_mock:
            return self.device.set_mode(mode)
        
        result = self._execute_command(f'M {mode} {bandwidth}')
        return result is not None
    
    def get_power(self):
        """
        Get transmit power level.
        
        Returns:
            float: Power level (0.0 - 1.0) or None
        """
        if self.use_mock:
            return self.device.get_power() / 100.0  # Convert to 0-1 range
        
        power = self._execute_command('l RFPOWER')
        if power:
            try:
                return float(power)
            except ValueError:
                return None
        return None
    
    def set_power(self, power_level):
        """
        Set transmit power level.
        
        Args:
            power_level: Power level (0.0 - 1.0)
            
        Returns:
            bool: True if successful
        """
        if self.use_mock:
            return self.device.set_power(power_level * 100)
        
        result = self._execute_command(f'L RFPOWER {power_level}')
        return result is not None
    
    def get_info(self):
        """
        Get comprehensive radio information.
        
        Returns:
            dict: Radio status information
        """
        return {
            'frequency': self.get_frequency(),
            'mode': self.get_mode(),
            'power': self.get_power(),
            'connected': self.is_connected()
        }

# Factory function
def get_radio_device(config):
    """
    Factory function to create radio device based on configuration.
    
    Args:
        config: Flask config object
        
    Returns:
        HamlibRadio: Configured radio device instance
    """
    return HamlibRadio(
        model=config.get('RADIO_MODEL', 1035),
        port=config.get('RADIO_PORT', '/dev/ttyUSB1'),
        baudrate=config.get('RADIO_BAUD_RATE', 38400),
        use_mock=config.get('USE_MOCK_DEVICES', True)
    )