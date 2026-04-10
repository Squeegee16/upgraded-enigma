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
    
    def connect(self):
        """Mock connect."""
        self.connected = True
        return True
    
    def disconnect(self):
        """Mock disconnect."""
        self.connected = False
    
    def is_connected(self):
        """Check mock connection."""
        return self.connected
    
    def get_position(self):
        """
        Get current GPS position.
        
        Returns:
            dict: Position data with lat, lon, altitude, grid, time
        """
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
    
    def connect(self):
        """Mock connect."""
        self.connected = True
        return True
    
    def disconnect(self):
        """Mock disconnect."""
        self.connected = False
    
    def is_connected(self):
        """Check mock connection."""
        return self.connected
    
    def get_frequency(self):
        """Get current frequency in MHz."""
        return self.frequency
    
    def set_frequency(self, freq_mhz):
        """Set frequency in MHz."""
        self.frequency = freq_mhz
        return True
    
    def get_mode(self):
        """Get current operating mode."""
        return self.mode
    
    def set_mode(self, mode):
        """Set operating mode."""
        self.mode = mode
        return True
    
    def get_power(self):
        """Get transmit power in watts."""
        return self.power
    
    def set_power(self, power_watts):
        """Set transmit power in watts."""
        self.power = power_watts
        return True

class MockSDRDevice(BaseDevice):
    """Mock RTL-SDR device for testing."""
    
    def __init__(self):
        super().__init__(use_mock=True)
        self.frequency = 144.500  # MHz
        self.sample_rate = 2048000
        self.gain = 20
    
    def connect(self):
        """Mock connect."""
        self.connected = True
        return True
    
    def disconnect(self):
        """Mock disconnect."""
        self.connected = False
    
    def is_connected(self):
        """Check mock connection."""
        return self.connected
    
    def get_frequency(self):
        """Get center frequency in MHz."""
        return self.frequency
    
    def set_frequency(self, freq_mhz):
        """Set center frequency in MHz."""
        self.frequency = freq_mhz
        return True
    
    def get_sample_rate(self):
        """Get sample rate in Hz."""
        return self.sample_rate
    
    def set_sample_rate(self, rate):
        """Set sample rate in Hz."""
        self.sample_rate = rate
        return True
    
    def read_samples(self, num_samples):
        """
        Read IQ samples from SDR.
        
        Returns mock random samples for testing.
        """
        import numpy as np
        # Return random complex samples
        return np.random.randn(num_samples) + 1j * np.random.randn(num_samples)