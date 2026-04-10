"""
SDR Monitor Plugin
==================
Integration with sdr-monitor for spectrum monitoring.
GitHub: https://github.com/shajen/sdr-monitor
"""

from plugins.base import BasePlugin
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
import requests
import subprocess
import os
import signal

class SDRMonitorPlugin(BasePlugin):
    """
    SDR Monitor plugin for spectrum monitoring and signal detection.
    
    This plugin integrates with the sdr-monitor project to provide
    real-time spectrum monitoring, signal detection, and recording.
    """
    
    name = "SDR Monitor"
    description = "Real-time spectrum monitoring and signal detection using RTL-SDR"
    version = "1.0.0"
    author = "Ham Radio App Team"
    
    def __init__(self, app=None, devices=None):
        super().__init__(app, devices)
        self.sdr_monitor_process = None
        self.sdr_monitor_url = "http://localhost:8080"
        self.sdr_device = None
    
    def initialize(self):
        """Initialize SDR Monitor plugin."""
        try:
            # Get SDR device
            self.sdr_device = self.get_device('sdr')
            
            if self.sdr_device:
                self.sdr_device.connect()
            
            # Check if sdr-monitor is installed
            try:
                result = subprocess.run(
                    ['which', 'sdr-monitor'],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    print("Warning: sdr-monitor not found in PATH")
                    print("Please install from: https://github.com/shajen/sdr-monitor")
            except Exception as e:
                print(f"Error checking for sdr-monitor: {e}")
            
            return True
        except Exception as e:
            print(f"Error initializing SDR Monitor plugin: {e}")
            return False
    
    def shutdown(self):
        """Shutdown SDR Monitor plugin."""
        self.stop_monitoring()
        
        if self.sdr_device:
            self.sdr_device.disconnect()
    
    def get_blueprint(self):
        """Get Flask blueprint for SDR Monitor routes."""
        bp = Blueprint('SDR Monitor', __name__, url_prefix='/plugin/sdr-monitor')
        
        @bp.route('/')
        @login_required
        def index():
            """Main SDR Monitor page."""
            return render_template(
                'plugins/sdr_monitor.html',
                plugin=self,
                user=current_user
            )
        
        @bp.route('/start', methods=['POST'])
        @login_required
        def start_monitoring():
            """Start SDR monitoring."""
            try:
                data = request.get_json() or {}
                frequency = data.get('frequency', 144.5)
                sample_rate = data.get('sample_rate', 2048000)
                
                success = self.start_monitoring(frequency, sample_rate)
                
                return jsonify({
                    'success': success,
                    'message': 'Monitoring started' if success else 'Failed to start monitoring'
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @bp.route('/stop', methods=['POST'])
        @login_required
        def stop_monitoring():
            """Stop SDR monitoring."""
            try:
                self.stop_monitoring()
                return jsonify({'success': True, 'message': 'Monitoring stopped'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @bp.route('/spectrum')
        @login_required
        def get_spectrum():
            """Get current spectrum data."""
            try:
                if self.sdr_device and self.sdr_device.is_connected():
                    spectrum = self.sdr_device.get_spectrum()
                    return jsonify({'success': True, 'data': spectrum})
                else:
                    return jsonify({'success': False, 'error': 'SDR not connected'}), 503
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @bp.route('/status')
        @login_required
        def get_status():
            """Get monitoring status."""
            return jsonify({
                'monitoring': self.sdr_monitor_process is not None,
                'connected': self.sdr_device.is_connected() if self.sdr_device else False,
                'frequency': self.sdr_device.get_frequency() if self.sdr_device else None
            })
        
        @bp.route('/log_signal', methods=['POST'])
        @login_required
        def log_signal():
            """Log a detected signal to the logbook."""
            try:
                data = request.get_json()
                
                contact_data = {
                    'callsign': data.get('callsign', 'UNKNOWN'),
                    'mode': data.get('mode', 'SIGNAL'),
                    'band': self._frequency_to_band(data.get('frequency', 0)),
                    'frequency': data.get('frequency'),
                    'grid': data.get('grid'),
                    'rst_sent': data.get('rst_sent'),
                    'rst_rcvd': data.get('rst_rcvd'),
                    'notes': f"SDR Monitor detection: {data.get('notes', '')}"
                }
                
                success = self.log_contact(contact_data)
                
                return jsonify({
                    'success': success,
                    'message': 'Signal logged' if success else 'Failed to log signal'
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        return bp
    
    def start_monitoring(self, frequency=144.5, sample_rate=2048000):
        """
        Start SDR monitoring process.
        
        Args:
            frequency: Center frequency in MHz
            sample_rate: Sample rate in Hz
            
        Returns:
            bool: True if started successfully
        """
        try:
            # Stop existing monitoring if running
            self.stop_monitoring()
            
            # Set SDR parameters
            if self.sdr_device:
                self.sdr_device.set_frequency(frequency)
                self.sdr_device.set_sample_rate(sample_rate)
            
            # Start sdr-monitor process (if installed)
            # This is a placeholder - actual implementation depends on sdr-monitor configuration
            # cmd = [
            #     'sdr-monitor',
            #     '-f', str(int(frequency * 1e6)),
            #     '-s', str(sample_rate),
            #     '-p', '8080'
            # ]
            # self.sdr_monitor_process = subprocess.Popen(cmd)
            
            return True
        except Exception as e:
            print(f"Error starting monitoring: {e}")
            return False
    
    def stop_monitoring(self):
        """Stop SDR monitoring process."""
        if self.sdr_monitor_process:
            try:
                os.kill(self.sdr_monitor_process.pid, signal.SIGTERM)
                self.sdr_monitor_process.wait(timeout=5)
            except Exception as e:
                print(f"Error stopping monitoring: {e}")
            finally:
                self.sdr_monitor_process = None
    
    @staticmethod
    def _frequency_to_band(freq_mhz):
        """
        Convert frequency to band designation.
        
        Args:
            freq_mhz: Frequency in MHz
            
        Returns:
            str: Band designation (e.g., "2m", "70cm")
        """
        if freq_mhz < 2:
            return "160m"
        elif freq_mhz < 4:
            return "80m"
        elif freq_mhz < 7.5:
            return "40m"
        elif freq_mhz < 14.5:
            return "20m"
        elif freq_mhz < 21.5:
            return "15m"
        elif freq_mhz < 29.7:
            return "10m"
        elif freq_mhz < 54:
            return "6m"
        elif freq_mhz < 148:
            return "2m"
        elif freq_mhz < 450:
            return "70cm"
        else:
            return "UHF"