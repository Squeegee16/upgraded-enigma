"""
RTL-SDR Device Interface
========================
Interface for RTL-SDR USB devices.
Supports both real RTL-SDR hardware and mock for testing.
"""

from devices.base import BaseDevice, MockSDRDevice
import subprocess
import numpy as np

class RTLSDRDevice(BaseDevice):
    """
    RTL-SDR device interface.
    
    Uses rtl_sdr command-line tool or rtlsdr Python library
    for interfacing with RTL-SDR USB dongles.
    """
    
    def __init__(self, device_index=0, sample_rate=2048000, use_mock=False):
        """
        Initialize RTL-SDR device.
        
        Args:
            device_index: Device index (if multiple dongles)
            sample_rate: Sample rate in Hz
            use_mock: Use mock device if True
        """
        super().__init__(use_mock)
        
        if use_mock:
            self.device = MockSDRDevice()
        else:
            self.device_index = device_index
            self.sample_rate = sample_rate
            self.frequency = 100.0  # MHz
            self.gain = 20  # dB
    
    def connect(self):
        """Test connection to RTL-SDR device."""
        if self.use_mock:
            return self.device.connect()
        
        try:
            # Test by querying device info
            result = subprocess.run(
                ['rtl_test', '-t'],
                capture_output=True,
                text=True,
                timeout=5
            )
            self.connected = result.returncode == 0
            return self.connected
        except Exception as e:
            print(f"RTL-SDR connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from RTL-SDR."""
        if self.use_mock:
            return self.device.disconnect()
        
        self.connected = False
    
    def is_connected(self):
        """Check RTL-SDR connection status."""
        if self.use_mock:
            return self.device.is_connected()
        return self.connected
    
    def get_frequency(self):
        """Get center frequency in MHz."""
        if self.use_mock:
            return self.device.get_frequency()
        return self.frequency
    
    def set_frequency(self, freq_mhz):
        """
        Set center frequency.
        
        Args:
            freq_mhz: Frequency in MHz
            
        Returns:
            bool: True if successful
        """
        if self.use_mock:
            return self.device.set_frequency(freq_mhz)
        
        self.frequency = freq_mhz
        return True
    
    def get_sample_rate(self):
        """Get sample rate in Hz."""
        if self.use_mock:
            return self.device.get_sample_rate()
        return self.sample_rate
    
    def set_sample_rate(self, rate):
        """
        Set sample rate.
        
        Args:
            rate: Sample rate in Hz
            
        Returns:
            bool: True if successful
        """
        if self.use_mock:
            return self.device.set_sample_rate(rate)
        
        self.sample_rate = rate
        return True
    
    def set_gain(self, gain_db):
        """
        Set RF gain.
        
        Args:
            gain_db: Gain in dB
            
        Returns:
            bool: True if successful
        """
        if self.use_mock:
            self.device.gain = gain_db
            return True
        
        self.gain = gain_db
        return True
    
    def read_samples(self, num_samples=262144):
        """
        Read IQ samples from SDR.
        
        Args:
            num_samples: Number of samples to read
            
        Returns:
            numpy.ndarray: Complex IQ samples
        """
        if self.use_mock:
            return self.device.read_samples(num_samples)
        
        try:
            # Use rtl_sdr to capture samples
            freq_hz = int(self.frequency * 1_000_000)
            
            cmd = [
                'rtl_sdr',
                '-f', str(freq_hz),
                '-s', str(self.sample_rate),
                '-n', str(num_samples * 2),  # IQ = 2 samples per point
                '-g', str(self.gain),
                '-'  # Output to stdout
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # Convert bytes to IQ samples
                samples = np.frombuffer(result.stdout, dtype=np.uint8)
                # Convert to complex (I + jQ)
                iq = samples[::2] + 1j * samples[1::2]
                # Normalize to -1 to 1
                iq = (iq - 127.5) / 127.5
                return iq
            
            return None
        except Exception as e:
            print(f"RTL-SDR read error: {e}")
            return None
    
    def get_spectrum(self, num_samples=262144):
        """
        Get power spectrum from SDR.
        
        Args:
            num_samples: Number of samples for FFT
            
        Returns:
            dict: Spectrum data with frequencies and power
        """
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

# Factory function
def get_sdr_device(config):
    """
    Factory function to create SDR device based on configuration.
    
    Args:
        config: Flask config object
        
    Returns:
        RTLSDRDevice: Configured SDR device instance
    """
    return RTLSDRDevice(
        device_index=config.get('SDR_DEVICE_INDEX', 0),
        sample_rate=config.get('SDR_SAMPLE_RATE', 2048000),
        use_mock=config.get('USE_MOCK_DEVICES', True)
    )