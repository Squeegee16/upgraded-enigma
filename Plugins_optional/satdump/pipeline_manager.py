"""
SatDump Pipeline Manager
=========================
Manages SatDump processing pipelines for satellite data.

SatDump Pipelines:
    A pipeline defines the complete processing chain for
    a specific satellite and data type, from raw SDR
    samples to processed images and data products.

    Each pipeline specifies:
    - Input source (SDR device, file, network)
    - Satellite/signal type
    - Processing modules
    - Output products (images, data files)

Built-in Pipelines (examples):
    NOAA APT:
        noaa_apt - Full APT decoding pipeline
        Produces: APT images with map overlays
    NOAA HRPT:
        noaa_hrpt - HRPT/POES pipeline
        Produces: AVHRR channel images
    METEOR LRPT:
        meteor_m2_lrpt - METEOR-M2 LRPT
        Produces: MSU-MR channel images
    GOES LRIT:
        goes_lrit - GOES East/West
        Produces: Full-disk imagery
    Meteosat LRIT:
        meteosat_lrit - Meteosat MSG
        Produces: HRIT/LRIT products

SatDump CLI Usage:
    # Live SDR processing:
    satdump live <pipeline> <output_dir> --source rtlsdr
        --samplerate 2.048M --frequency 137.1M

    # File processing:
    satdump process <pipeline> <input_file> <output_dir>

Reference:
    https://docs.satdump.org/pipelines.html
    https://github.com/SatDump/SatDump/tree/master/pipelines
"""

import os
import json
import subprocess
import shutil
from datetime import datetime


class PipelineManager:
    """
    Manages SatDump pipeline definitions and execution.

    Provides pipeline discovery, configuration, and
    execution management for the plugin UI.
    """

    # Built-in satellite pipeline definitions
    # Maps friendly name -> SatDump pipeline ID
    PIPELINES = {
        # NOAA Weather Satellites (APT)
        'NOAA APT (137 MHz)': {
            'id': 'noaa_apt',
            'frequency': 137.1e6,
            'samplerate': 48000,
            'satellite': 'NOAA-15/18/19',
            'band': 'VHF',
            'description': 'NOAA APT weather images',
            'products': ['apt_image', 'map_overlay'],
            'source_type': 'rtlsdr',
        },
        'NOAA-15 APT': {
            'id': 'noaa_apt',
            'frequency': 137.62e6,
            'samplerate': 48000,
            'satellite': 'NOAA-15',
            'band': 'VHF',
            'description': 'NOAA-15 APT 137.620 MHz',
            'products': ['apt_image'],
            'source_type': 'rtlsdr',
        },
        'NOAA-18 APT': {
            'id': 'noaa_apt',
            'frequency': 137.9125e6,
            'samplerate': 48000,
            'satellite': 'NOAA-18',
            'band': 'VHF',
            'description': 'NOAA-18 APT 137.9125 MHz',
            'products': ['apt_image'],
            'source_type': 'rtlsdr',
        },
        'NOAA-19 APT': {
            'id': 'noaa_apt',
            'frequency': 137.1e6,
            'samplerate': 48000,
            'satellite': 'NOAA-19',
            'band': 'VHF',
            'description': 'NOAA-19 APT 137.100 MHz',
            'products': ['apt_image'],
            'source_type': 'rtlsdr',
        },
        # METEOR Weather Satellites
        'METEOR-M2 LRPT': {
            'id': 'meteor_m2_lrpt',
            'frequency': 137.9e6,
            'samplerate': 150000,
            'satellite': 'METEOR-M2',
            'band': 'VHF',
            'description': 'Russian METEOR LRPT weather images',
            'products': ['msu_mr_image'],
            'source_type': 'rtlsdr',
        },
        'METEOR-M2-3 LRPT': {
            'id': 'meteor_m2_lrpt',
            'frequency': 137.9e6,
            'samplerate': 150000,
            'satellite': 'METEOR-M2-3',
            'band': 'VHF',
            'description': 'METEOR-M2-3 LRPT weather images',
            'products': ['msu_mr_image'],
            'source_type': 'rtlsdr',
        },
        # NOAA HRPT (L-Band)
        'NOAA HRPT': {
            'id': 'noaa_hrpt',
            'frequency': 1698e6,
            'samplerate': 3e6,
            'satellite': 'NOAA POES',
            'band': 'L-Band',
            'description': 'NOAA HRPT high-resolution images',
            'products': ['avhrr_image'],
            'source_type': 'rtlsdr',
        },
        # GOES Satellites
        'GOES-16 LRIT': {
            'id': 'goes_lrit',
            'frequency': 1694.1e6,
            'samplerate': 4e6,
            'satellite': 'GOES-16',
            'band': 'L-Band',
            'description': 'GOES-16 East full-disk imagery',
            'products': ['lrit_images'],
            'source_type': 'rtlsdr',
        },
        'GOES-18 LRIT': {
            'id': 'goes_lrit',
            'frequency': 1694.1e6,
            'samplerate': 4e6,
            'satellite': 'GOES-18',
            'band': 'L-Band',
            'description': 'GOES-18 West full-disk imagery',
            'products': ['lrit_images'],
            'source_type': 'rtlsdr',
        },
        # FengYun Chinese Satellites
        'FengYun-3 LRPT': {
            'id': 'fy3_mrpt',
            'frequency': 137.1e6,
            'samplerate': 150000,
            'satellite': 'FY-3',
            'band': 'VHF',
            'description': 'Chinese FengYun-3 weather images',
            'products': ['mersi_image'],
            'source_type': 'rtlsdr',
        },
        # SSTV from the ISS
        'ISS SSTV': {
            'id': 'iss_sstv',
            'frequency': 145.8e6,
            'samplerate': 48000,
            'satellite': 'ISS',
            'band': 'VHF',
            'description': 'ISS SSTV transmissions 145.800 MHz',
            'products': ['sstv_image'],
            'source_type': 'rtlsdr',
        },
        # Generic LRPT
        'Generic LRPT': {
            'id': 'generic_lrpt',
            'frequency': 137.9e6,
            'samplerate': 150000,
            'satellite': 'Generic',
            'band': 'VHF',
            'description': 'Generic LRPT receiver',
            'products': ['images'],
            'source_type': 'rtlsdr',
        },
    }

    # SDR source types supported by SatDump
    SDR_SOURCES = {
        'rtlsdr': {
            'name': 'RTL-SDR',
            'param': 'rtlsdr',
            'extra_params': [
                '--source_id', '0',
                '--gain', '49'
            ]
        },
        'airspy': {
            'name': 'Airspy',
            'param': 'airspy',
            'extra_params': [
                '--gain', '18'
            ]
        },
        'hackrf': {
            'name': 'HackRF',
            'param': 'hackrf',
            'extra_params': []
        },
        'sdrplay': {
            'name': 'SDRplay',
            'param': 'sdrplay',
            'extra_params': [
                '--gain', '0'
            ]
        },
        'plutosdr': {
            'name': 'PlutoSDR',
            'param': 'plutosdr',
            'extra_params': [
                '--addr', 'ip:192.168.2.1'
            ]
        },
        'spyserver': {
            'name': 'SpyServer',
            'param': 'spyserver',
            'extra_params': [
                '--host', 'localhost',
                '--port', '5555'
            ]
        },
        'file': {
            'name': 'IQ File',
            'param': 'file',
            'extra_params': []
        },
    }

    def __init__(self, satdump_binary=None):
        """
        Initialize pipeline manager.

        Args:
            satdump_binary: Path to satdump executable
        """
        self.satdump_binary = (
            satdump_binary or shutil.which('satdump')
        )
        self._dynamic_pipelines = {}

        # Try to load additional pipelines from SatDump
        self._load_satdump_pipelines()

    def _load_satdump_pipelines(self):
        """
        Load pipeline definitions from SatDump installation.

        SatDump stores pipeline JSON files in its data
        directory. Try to parse these for complete list.
        """
        pipeline_dirs = [
            '/usr/share/satdump/pipelines',
            '/usr/local/share/satdump/pipelines',
            os.path.expanduser('~/.config/satdump/pipelines'),
            '/opt/satdump/pipelines',
        ]

        loaded_count = 0
        for pipeline_dir in pipeline_dirs:
            if os.path.exists(pipeline_dir):
                try:
                    for filename in os.listdir(pipeline_dir):
                        if filename.endswith('.json'):
                            filepath = os.path.join(
                                pipeline_dir, filename
                            )
                            count = self._parse_pipeline_file(
                                filepath
                            )
                            loaded_count += count
                    if loaded_count > 0:
                        print(
                            f"[SatDump] Loaded {loaded_count} "
                            f"pipelines from {pipeline_dir}"
                        )
                        break
                except Exception as e:
                    print(
                        f"[SatDump] Pipeline load error: {e}"
                    )

    def _parse_pipeline_file(self, filepath):
        """
        Parse a SatDump pipeline JSON file.

        Args:
            filepath: Path to pipeline JSON file

        Returns:
            int: Number of pipelines loaded
        """
        loaded = 0
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            # Pipeline files may contain single or multiple defs
            if isinstance(data, dict):
                pipelines = [data]
            elif isinstance(data, list):
                pipelines = data
            else:
                return 0

            for pipeline in pipelines:
                name = pipeline.get('name', '')
                pipeline_id = pipeline.get('id', '')

                if name and pipeline_id:
                    self._dynamic_pipelines[name] = {
                        'id': pipeline_id,
                        'frequency': pipeline.get(
                            'frequency', 137e6
                        ),
                        'samplerate': pipeline.get(
                            'samplerate', 2.048e6
                        ),
                        'satellite': pipeline.get(
                            'name', 'Unknown'
                        ),
                        'description': pipeline.get(
                            'description', ''
                        ),
                        'products': [],
                        'source_type': 'rtlsdr',
                        'from_satdump': True
                    }
                    loaded += 1

        except Exception as e:
            print(f"[SatDump] Pipeline parse error: {e}")

        return loaded

    def get_all_pipelines(self):
        """
        Get all available pipelines.

        Returns built-in pipelines plus any loaded from
        SatDump installation.

        Returns:
            dict: All pipeline definitions
        """
        all_pipelines = dict(self.PIPELINES)
        all_pipelines.update(self._dynamic_pipelines)
        return all_pipelines

    def get_pipeline(self, name):
        """
        Get a specific pipeline by name.

        Args:
            name: Pipeline friendly name

        Returns:
            dict: Pipeline definition or None
        """
        return self.get_all_pipelines().get(name)

    def get_pipelines_by_band(self, band):
        """
        Get pipelines filtered by frequency band.

        Args:
            band: Band name (VHF, L-Band, etc.)

        Returns:
            dict: Filtered pipelines
        """
        return {
            name: p for name, p in self.get_all_pipelines().items()
            if p.get('band', '').upper() == band.upper()
        }

    def build_command(self, pipeline_name, output_dir,
                      source_override=None,
                      frequency_override=None,
                      extra_args=None):
        """
        Build a SatDump CLI command for a pipeline.

        Constructs the complete command line for running
        a SatDump live pipeline from the given parameters.

        Args:
            pipeline_name: Name of pipeline to run
            output_dir: Directory for output products
            source_override: SDR source to use
            frequency_override: Frequency override in Hz
            extra_args: Additional CLI arguments

        Returns:
            list: Command and arguments, or None on error
        """
        pipeline = self.get_pipeline(pipeline_name)
        if not pipeline:
            print(f"[SatDump] Pipeline not found: {pipeline_name}")
            return None

        if not self.satdump_binary:
            print("[SatDump] satdump binary not found")
            return None

        # Get source configuration
        source_key = source_override or pipeline.get(
            'source_type', 'rtlsdr'
        )
        source_config = self.SDR_SOURCES.get(
            source_key, self.SDR_SOURCES['rtlsdr']
        )

        # Get frequency
        frequency = frequency_override or pipeline.get(
            'frequency', 137.1e6
        )

        # Get sample rate
        samplerate = pipeline.get('samplerate', 2.048e6)

        # Build base command
        cmd = [
            self.satdump_binary,
            'live',
            pipeline['id'],           # Pipeline ID
            output_dir,               # Output directory
            '--source', source_config['param'],
            '--samplerate', self._format_rate(samplerate),
            '--frequency', str(int(frequency)),
        ]

        # Add source-specific parameters
        cmd.extend(source_config.get('extra_params', []))

        # Add any extra arguments
        if extra_args:
            cmd.extend(extra_args)

        return cmd

    def build_offline_command(self, pipeline_name, input_file,
                               output_dir, extra_args=None):
        """
        Build a SatDump command for offline file processing.

        Args:
            pipeline_name: Pipeline to use
            input_file: Input IQ recording file
            output_dir: Output directory
            extra_args: Additional arguments

        Returns:
            list: Command arguments or None
        """
        pipeline = self.get_pipeline(pipeline_name)
        if not pipeline or not self.satdump_binary:
            return None

        cmd = [
            self.satdump_binary,
            'process',              # Process mode (not live)
            pipeline['id'],
            input_file,
            output_dir,
        ]

        if extra_args:
            cmd.extend(extra_args)

        return cmd

    @staticmethod
    def _format_rate(rate):
        """
        Format sample rate for SatDump command line.

        Args:
            rate: Sample rate in Hz (float or int)

        Returns:
            str: Formatted rate string (e.g., '2.048M')
        """
        rate = float(rate)
        if rate >= 1e6:
            return f"{rate/1e6:.3f}M"
        elif rate >= 1e3:
            return f"{rate/1e3:.3f}K"
        else:
            return str(int(rate))

    def get_satellites_by_category(self):
        """
        Get pipelines organized by satellite category.

        Returns:
            dict: Category -> list of pipeline names
        """
        categories = {
            'VHF Weather (APT/LRPT)': [],
            'L-Band Weather': [],
            'Geostationary': [],
            'Amateur': [],
            'Other': []
        }

        for name, pipeline in self.get_all_pipelines().items():
            band = pipeline.get('band', 'Other')
            sat = pipeline.get('satellite', '').upper()

            if 'NOAA' in sat and band == 'VHF':
                categories['VHF Weather (APT/LRPT)'].append(name)
            elif 'METEOR' in sat or 'FENGYU' in sat:
                categories['VHF Weather (APT/LRPT)'].append(name)
            elif 'GOES' in sat or 'METEOSAT' in sat:
                categories['Geostationary'].append(name)
            elif band == 'L-Band':
                categories['L-Band Weather'].append(name)
            elif 'ISS' in sat or sat == 'AMATEUR':
                categories['Amateur'].append(name)
            else:
                categories['Other'].append(name)

        # Remove empty categories
        return {k: v for k, v in categories.items() if v}