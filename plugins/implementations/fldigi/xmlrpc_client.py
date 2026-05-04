"""
FLdigi XML-RPC Client
======================
Wrapper around Python's xmlrpc.client for communicating
with the FLdigi XML-RPC server.

FLdigi exposes its API on port 7362 by default.
All API methods are available via XML-RPC protocol.

API Categories:
    fldigi.*        - General FLdigi control
    modem.*         - Modem/mode selection and control
    main.*          - Main window and frequency control
    log.*           - Log entries and macros
    text.*          - TX/RX text buffer access
    rig.*           - Radio/rig control interface
    spot.*          - DX cluster spot handling
    wefax.*         - Wefax mode control
    navtex.*        - NAVTEX mode control
    io.*            - I/O channel control

Reference:
    http://www.w1hkj.com/FldigiHelp/xmlrpc-control.html
"""

import xmlrpc.client
import socket
from datetime import datetime


class FldigiXMLRPC:
    """
    FLdigi XML-RPC API client.

    Wraps all major FLdigi XML-RPC methods with error
    handling and connection state management.

    Usage:
        client = FldigiXMLRPC(host='localhost', port=7362)
        if client.connect():
            version = client.get_version()
            client.set_frequency(14074000)
    """

    def __init__(self, host='localhost', port=7362):
        """
        Initialize XML-RPC client.

        Args:
            host: FLdigi host address (default: localhost)
            port: FLdigi XML-RPC port (default: 7362)
        """
        self.host = host
        self.port = port
        self.url = f'http://{host}:{port}/RPC2'
        self._server = None
        self._connected = False

    def connect(self):
        """
        Establish connection to FLdigi XML-RPC server.

        Returns:
            bool: True if connection successful
        """
        try:
            self._server = xmlrpc.client.ServerProxy(
                self.url,
                allow_none=True
            )

            # Test connection by calling fldigi.version()
            version = self._server.fldigi.version()
            self._connected = True
            print(f"[FLdigi-XMLRPC] Connected: FLdigi {version}")
            return True

        except ConnectionRefusedError:
            self._connected = False
            return False
        except Exception as e:
            self._connected = False
            print(f"[FLdigi-XMLRPC] Connection error: {e}")
            return False

    def disconnect(self):
        """Close XML-RPC connection."""
        self._server = None
        self._connected = False

    def is_connected(self):
        """
        Check if XML-RPC connection is active.

        Returns:
            bool: True if connected and responding
        """
        if not self._server:
            return False

        try:
            self._server.fldigi.version()
            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    def _call(self, method_path, *args, default=None):
        """
        Execute an XML-RPC method with error handling.

        Args:
            method_path: Dot-separated method path
                        (e.g., 'modem.get_name')
            *args: Method arguments
            default: Default value on error

        Returns:
            Method return value or default on error
        """
        if not self._server:
            return default

        try:
            # Traverse method path on server proxy
            parts = method_path.split('.')
            method = self._server

            for part in parts:
                method = getattr(method, part)

            return method(*args)

        except xmlrpc.client.Fault as e:
            print(f"[FLdigi-XMLRPC] Fault in {method_path}: {e}")
            return default
        except ConnectionRefusedError:
            self._connected = False
            return default
        except Exception as e:
            print(f"[FLdigi-XMLRPC] Error in {method_path}: {e}")
            return default

    # ================================================================
    # FLdigi General Methods
    # ================================================================

    def get_version(self):
        """
        Get FLdigi version string.

        Returns:
            str: Version string or None
        """
        return self._call('fldigi.version')

    def get_name(self):
        """
        Get FLdigi application name.

        Returns:
            str: Application name
        """
        return self._call('fldigi.name', default='fldigi')

    def terminate(self, save_options=True):
        """
        Request FLdigi to terminate.

        Args:
            save_options: Save options on exit

        Returns:
            str: Response or None
        """
        return self._call(
            'fldigi.terminate',
            int(save_options)
        )

    # ================================================================
    # Modem Methods
    # ================================================================

    def get_modem_name(self):
        """
        Get current modem/mode name.

        Returns:
            str: Mode name (e.g., 'PSK31', 'RTTY')
        """
        return self._call('modem.get_name', default='')

    def get_modem_names(self):
        """
        Get list of all available modem names.

        Returns:
            list: Available mode names
        """
        result = self._call('modem.get_names', default=[])
        return list(result) if result else []

    def set_modem_by_name(self, name):
        """
        Set modem by mode name.

        Args:
            name: Mode name string (e.g., 'PSK31')

        Returns:
            str: Response or None
        """
        return self._call('modem.set_by_name', name)

    def get_modem_id(self):
        """
        Get current modem ID.

        Returns:
            int: Modem ID number
        """
        return self._call('modem.get_id', default=0)

    def set_modem_by_id(self, modem_id):
        """
        Set modem by numeric ID.

        Args:
            modem_id: Integer modem ID

        Returns:
            str: Response or None
        """
        return self._call('modem.set_by_id', modem_id)

    def get_modem_bandwidth(self):
        """
        Get current modem bandwidth in Hz.

        Returns:
            int: Bandwidth in Hz
        """
        return self._call('modem.get_bandwidth', default=0)

    def get_modem_carrier(self):
        """
        Get current modem carrier frequency offset in Hz.

        Returns:
            int: Carrier offset in Hz
        """
        return self._call('modem.get_carrier', default=1500)

    def set_modem_carrier(self, carrier):
        """
        Set modem carrier frequency offset.

        Args:
            carrier: Carrier offset in Hz

        Returns:
            str: Response
        """
        return self._call('modem.set_carrier', carrier)

    def get_squelch(self):
        """
        Get squelch state.

        Returns:
            bool: True if squelch is enabled
        """
        return bool(self._call('modem.get_squelch', default=False))

    def set_squelch(self, enabled):
        """
        Set squelch state.

        Args:
            enabled: True to enable squelch
        """
        self._call('modem.set_squelch', int(enabled))

    def get_squelch_level(self):
        """
        Get squelch level.

        Returns:
            float: Squelch level
        """
        return self._call('modem.get_squelch_level', default=0.0)

    def set_squelch_level(self, level):
        """
        Set squelch level.

        Args:
            level: Float squelch level value
        """
        self._call('modem.set_squelch_level', level)

    # ================================================================
    # Main Window / Frequency Methods
    # ================================================================

    def get_frequency(self):
        """
        Get current rig frequency in Hz.

        Returns:
            int: Frequency in Hz
        """
        return self._call('main.get_frequency', default=0)

    def set_frequency(self, freq_hz):
        """
        Set rig frequency.

        Args:
            freq_hz: Frequency in Hz

        Returns:
            float: Set frequency
        """
        return self._call('main.set_frequency', float(freq_hz))

    def get_wf_sideband(self):
        """
        Get waterfall sideband (USB/LSB).

        Returns:
            str: 'USB' or 'LSB'
        """
        return self._call('main.get_wf_sideband', default='USB')

    def set_wf_sideband(self, sideband):
        """
        Set waterfall sideband.

        Args:
            sideband: 'USB' or 'LSB'
        """
        self._call('main.set_wf_sideband', sideband)

    def get_status1(self):
        """
        Get status bar text line 1.

        Returns:
            str: Status text
        """
        return self._call('main.get_status1', default='')

    def get_status2(self):
        """
        Get status bar text line 2.

        Returns:
            str: Status text
        """
        return self._call('main.get_status2', default='')

    def get_trx_status(self):
        """
        Get transmit/receive status.

        Returns:
            str: 'rx', 'tx', or 'tune'
        """
        return self._call('main.get_trx_status', default='rx')

    def set_tx(self):
        """Switch to transmit mode."""
        self._call('main.tx')

    def set_rx(self):
        """Switch to receive mode."""
        self._call('main.rx')

    def set_tune(self):
        """Enable tune/carrier output."""
        self._call('main.tune')

    def abort(self):
        """Abort current transmission."""
        self._call('main.abort')

    # ================================================================
    # Text Buffer Methods
    # ================================================================

    def get_rx_text(self):
        """
        Get received text from RX buffer.

        Returns:
            str: Received text content
        """
        return self._call('text.get_rx_length',
                          default='') or ''

    def add_tx_text(self, text):
        """
        Add text to the TX buffer.

        Args:
            text: Text to transmit

        Returns:
            str: Response
        """
        return self._call('text.add_tx', text)

    def clear_tx_text(self):
        """Clear the TX text buffer."""
        self._call('text.clear_tx')

    def get_rx_text_full(self):
        """
        Get all text from RX buffer.

        Returns:
            str: All received text
        """
        length = self._call('text.get_rx_length', default=0)
        if not length:
            return ''
        return self._call(
            'text.get_rx', 0, int(length),
            default=''
        ) or ''

    # ================================================================
    # Log Methods
    # ================================================================

    def get_log_callsign(self):
        """
        Get callsign from FLdigi log panel.

        Returns:
            str: Callsign
        """
        return self._call('log.get_call', default='')

    def get_log_name(self):
        """
        Get name from FLdigi log panel.

        Returns:
            str: Contact name
        """
        return self._call('log.get_name', default='')

    def get_log_frequency(self):
        """
        Get frequency from FLdigi log panel.

        Returns:
            str: Frequency string
        """
        return self._call('log.get_frequency', default='')

    def get_log_mode(self):
        """
        Get mode from FLdigi log panel.

        Returns:
            str: Mode string
        """
        return self._call('log.get_mode', default='')

    def get_log_rst_in(self):
        """
        Get received RST from FLdigi log panel.

        Returns:
            str: RST received
        """
        return self._call('log.get_rst_in', default='')

    def get_log_rst_out(self):
        """
        Get sent RST from FLdigi log panel.

        Returns:
            str: RST sent
        """
        return self._call('log.get_rst_out', default='')

    def get_log_serial_out(self):
        """
        Get sent serial number.

        Returns:
            str: Serial number
        """
        return self._call('log.get_serial_out', default='')

    def get_log_gridsquare(self):
        """
        Get grid square from log panel.

        Returns:
            str: Maidenhead grid locator
        """
        return self._call('log.get_gridsquare', default='')

    def get_log_exchange(self):
        """
        Get exchange from log panel.

        Returns:
            str: Contest exchange
        """
        return self._call('log.get_exchange', default='')

    def set_log_callsign(self, callsign):
        """Set callsign in FLdigi log panel."""
        self._call('log.set_call', callsign)

    def set_log_rst_in(self, rst):
        """Set received RST in log panel."""
        self._call('log.set_rst_in', rst)

    def set_log_rst_out(self, rst):
        """Set sent RST in log panel."""
        self._call('log.set_rst_out', rst)

    def clear_log(self):
        """Clear FLdigi log panel fields."""
        self._call('log.clear')

    def save_log(self):
        """Save current log entry in FLdigi."""
        self._call('log.disp_qsylist')

    def get_full_log_entry(self):
        """
        Get complete log entry from FLdigi log panel.

        Reads all available log fields and returns as dict.

        Returns:
            dict: Complete log entry data
        """
        return {
            'callsign': self.get_log_callsign(),
            'name': self.get_log_name(),
            'frequency': self.get_log_frequency(),
            'mode': self.get_log_mode(),
            'rst_in': self.get_log_rst_in(),
            'rst_out': self.get_log_rst_out(),
            'gridsquare': self.get_log_gridsquare(),
            'exchange': self.get_log_exchange(),
            'timestamp': datetime.utcnow().isoformat()
        }

    # ================================================================
    # Rig Control Methods
    # ================================================================

    def get_rig_name(self):
        """
        Get connected rig/radio name.

        Returns:
            str: Rig name or empty string
        """
        return self._call('rig.get_name', default='')

    def get_rig_frequency(self):
        """
        Get rig frequency in Hz.

        Returns:
            int: Rig frequency in Hz
        """
        return self._call('rig.get_frequency', default=0)

    def set_rig_frequency(self, freq_hz):
        """
        Set rig frequency.

        Args:
            freq_hz: Frequency in Hz
        """
        self._call('rig.set_frequency', float(freq_hz))

    def get_rig_mode(self):
        """
        Get rig operating mode.

        Returns:
            str: Mode string
        """
        return self._call('rig.get_mode', default='')

    def set_rig_mode(self, mode):
        """
        Set rig operating mode.

        Args:
            mode: Mode string
        """
        self._call('rig.set_mode', mode)

    # ================================================================
    # Spot Methods (DX Spots)
    # ================================================================

    def get_spot_count(self):
        """
        Get number of DX spots.

        Returns:
            int: Number of spots
        """
        return self._call('spot.get_spot_count', default=0)

    def get_spot(self, n):
        """
        Get DX spot by index.

        Args:
            n: Spot index number

        Returns:
            dict: Spot data or None
        """
        return self._call('spot.get_spot', n)

    def get_all_spots(self):
        """
        Get all current DX spots.

        Returns:
            list: All spot entries
        """
        count = self.get_spot_count()
        spots = []

        for i in range(count):
            spot = self.get_spot(i)
            if spot:
                spots.append(spot)

        return spots