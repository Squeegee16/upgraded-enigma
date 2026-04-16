"""
Base Device Interface
=====================
Abstract base class for all device interfaces.
Provides mock implementations for testing.
"""

from abc import ABC, abstractmethod
from datetime import datetime
import random

class BaseDevice(ABC):
    """Abstract base class for device interfaces."""
    
    def __init__(self, use_mock=False):
        """
        Initialize device interface.
        
        Args:
            use_mock: If True, use mock implementation
        """
        self.use_mock = use_mock
        self.connected = False
    
    @abstractmethod
    def connect(self):
        """Establish connection to device."""
        pass
    
    @abstractmethod
    def disconnect(self):
        """Close connection to device."""
        pass
    
    @abstractmethod
    def is_connected(self):
        """Check if device is connected."""
        pass

class MockGPSDevice(BaseDevice):
    """Mock GPS device for testing."""
    
    def __init__(self):
        super().__init__(use_mock=True)
        self.latitude = 40.7128
        self.longitude = -74.0060
        self.altitude = 10.0
        self.grid = "FN20"
        self.connected = False  # Initialize as disconnected
    
    def connect(self):
        """Mock connect - always succeeds."""
        self.connected = True
        print("Mock GPS device connected")
        return True
    
    def disconnect(self):
        """Mock disconnect."""
        self.connected = False
        print("Mock GPS device disconnected")
    
    def is_connected(self):
        """Check mock connection."""
        return self.connected
    
    def get_position(self):
        """
        Get current GPS position.
        
        Returns:
            dict: Position data with lat, lon, altitude, grid, time
        """
        if not self.connected:
            return None
            
        # Simulate slight position drift
        lat_drift = random.uniform(-0.0001, 0.0001)
        lon_drift = random.uniform(-0.0001, 0.0001)
        
        return {
            'latitude': self.latitude + lat_drift,
            'longitude': self.longitude + lon_drift,
            'altitude': self.altitude,
            'grid': self.grid,
            'time': datetime.utcnow().isoformat(),
            'satellites': random.randint(6, 12)
        }

class MockRadioDevice(BaseDevice):
    """Mock radio device for testing."""
    
    def __init__(self):
        super().__init__(use_mock=True)
        self.frequency = 14.074  # MHz
        self.mode = 'USB'
        self.power = 100  # Watts
        self.connected = False  # Initialize as disconnected
    
    def connect(self):
        """Mock connect - always succeeds."""
        self.connected = True
        print("Mock radio device connected")
        return True
    
    def disconnect(self):
        """Mock disconnect."""
        self.connected = False
        print("Mock radio device disconnected")
    
    def is_connected(self):
        """Check mock connection."""
        return self.connected
    
    def get_frequency(self):
        """Get current frequency in MHz."""
        if not self.connected:
            return None
        return self.frequency
    
    def set_frequency(self, freq_mhz):
        """Set frequency in MHz."""
        if not self.connected:
            return False
        self.frequency = freq_mhz
        return True
    
    def get_mode(self):
        """Get current operating mode."""
        if not self.connected:
            return None
        return self.mode
    
    def set_mode(self, mode):
        """Set operating mode."""
        if not self.connected:
            return False
        self.mode = mode
        return True
    
    def get_power(self):
        """Get transmit power in watts."""
        if not self.connected:
            return None
        return self.power
    
    def set_power(self, power_watts):
        """Set transmit power in watts."""
        if not self.connected:
            return False
        self.power = power_watts
        return True
    
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

class MockSDRDevice(BaseDevice):
    """Mock RTL-SDR device for testing."""
    
    def __init__(self):
        super().__init__(use_mock=True)
        self.frequency = 144.500  # MHz
        self.sample_rate = 2048000
        self.gain = 20
        self.connected = False  # Initialize as disconnected
    
    def connect(self):
        """Mock connect - always succeeds."""
        self.connected = True
        print("Mock SDR device connected")
        return True
    
    def disconnect(self):
        """Mock disconnect."""
        self.connected = False
        print("Mock SDR device disconnected")
    
    def is_connected(self):
        """Check mock connection."""
        return self.connected
    
    def get_frequency(self):
        """Get center frequency in MHz."""
        if not self.connected:
            return None
        return self.frequency
    
    def set_frequency(self, freq_mhz):
        """Set center frequency in MHz."""
        if not self.connected:
            return False
        self.frequency = freq_mhz
        return True
    
    def get_sample_rate(self):
        """Get sample rate in Hz."""
        if not self.connected:
            return None
        return self.sample_rate
    
    def set_sample_rate(self, rate):
        """Set sample rate in Hz."""
        if not self.connected:
            return False
        self.sample_rate = rate
        return True
    
    def read_samples(self, num_samples):
        """
        Read IQ samples from SDR.
        
        Returns mock random samples for testing.
        """
        if not self.connected:
            return None
            
        try:
            import numpy as np
            # Return random complex samples
            return np.random.randn(num_samples) + 1j * np.random.randn(num_samples)
        except ImportError:
            # If numpy not available, return list of complex numbers
            return [complex(random.random(), random.random()) for _ in range(num_samples)]
    
    def get_spectrum(self, num_samples=262144):
        """
        Get power spectrum from SDR.
        
        Args:
            num_samples: Number of samples for FFT
            
        Returns:
            dict: Spectrum data with frequencies and power
        """
        if not self.connected:
            return None
            
        try:
            import numpy as np
            
            samples = self.read_samples(num_samples)
            
            if samples is None:
                return None
            
            # Compute FFT
            fft = np.fft.fft(samples)
            fft_shifted = np.fft.fftshift(fft)
            
            # Compute power spectrum in dB
            power_db = 20 * np.log10(np.abs(fft_shifted) + 1e-10)
            
            # Generate frequency axis
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1/self.sample_rate))
            freqs_mhz = freqs / 1_000_000 + self.frequency
            
            return {
                'frequencies': freqs_mhz.tolist(),
                'power': power_db.tolist(),
                'center_frequency': self.frequency,
                'sample_rate': self.sample_rate
            }
        except ImportError:
            # Simple mock spectrum without numpy
            num_points = 100
            frequencies = [self.frequency + (i - 50) * 0.01 for i in range(num_points)]
            power = [random.uniform(-100, -40) for _ in range(num_points)]
            
            return {
                'frequencies': frequencies,
                'power': power,
                'center_frequency': self.frequency,
                'sample_rate': self.sample_rate
            }
