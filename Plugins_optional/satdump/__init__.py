"""
SatDump Plugin Package
=======================
SatDump satellite data processing integration for the
Ham Radio Web Application.

SatDump is a comprehensive satellite data processing
application supporting:

Weather Satellites:
    NOAA APT (137 MHz):
        - NOAA-15, NOAA-18, NOAA-19
        - Automatic Picture Transmission
    NOAA HRPT (1.7 GHz):
        - High Resolution Picture Transmission
    METEOR-M (137 MHz):
        - Russian weather satellite series
        - LRPT (Low Rate Picture Transmission)
    Meteosat MSG (1.7 GHz):
        - European geostationary weather satellite
    FengYun (Chinese weather satellites)

Amateur Satellites:
    Linear transponders:
        - SSB/CW operations
    Digipeaters:
        - AX.25 packet repeaters
    APRS satellites:
        - Automatic Position Reporting
    CubeSats:
        - Educational/experimental satellites

Environmental/Science:
    GOES (Geostationary Operational Environmental Satellites)
    Himawari (Japanese weather satellite)
    Electro-L (Russian geostationary satellite)
    JPSS/Suomi NPP (Joint Polar Satellite System)

SDR Hardware Supported:
    - RTL-SDR
    - Airspy / Airspy HF+
    - SDRplay (RSP series)
    - HackRF One
    - PlutoSDR
    - LimeSDR
    - BladeRF
    - Various others via SoapySDR

Communication Methods:
    SatDump uses several interfaces:
    - Command line for batch processing
    - HTTP API server (optional)
    - File system for pipeline output
    - Process monitoring via psutil

Source: https://github.com/SatDump/SatDump
Documentation: https://docs.satdump.org/

Installation:
    Copy satdump/ directory to plugins/implementations/
    Dependencies installed automatically on first run.

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.satdump.plugin import SatDumpPlugin

# Export for automatic plugin discovery
__all__ = ['SatDumpPlugin']