"""
WSJT-X UDP Listener
====================
Listens to WSJT-X UDP multicast stream and decodes packets.

WSJT-X broadcasts status and decode data via UDP on
port 2237 by default. Multiple applications can listen
simultaneously by joining the multicast group.

Default Configuration:
    Host: localhost (or 0.0.0.0 for network access)
    Port: 2237
    Multicast: Optional (single-cast by default)

Thread Safety:
    Uses threading.Lock for shared data structures.
    Background thread reads UDP socket continuously.

Reference:
    https://github.com/WSJTX/wsjtx/blob/master/Network/NetworkMessage.hpp
"""

import socket
import threading
import time
from datetime import datetime
from collections import deque

from plugins.implementations.wsjtx.packet_decoder import (
    WSJTXPacketDecoder
)


class WSJTXUDPListener:
    """
    Background UDP listener for WSJT-X data stream.

    Receives UDP packets from WSJT-X, decodes them,
    and maintains queues of received data for the
    plugin to consume.
    """

    def __init__(self, host='0.0.0.0', port=2237,
                 multicast_group=None):
        """
        Initialize UDP listener.

        Args:
            host: IP address to bind to
            port: UDP port number (WSJT-X default: 2237)
            multicast_group: Multicast group IP or None
        """
        self.host = host
        self.port = port
        self.multicast_group = multicast_group

        # Packet decoder
        self.decoder = WSJTXPacketDecoder()

        # Thread control
        self._thread = None
        self._running = False
        self._lock = threading.Lock()

        # Data queues (deque for thread-safe FIFO)
        self._decodes = deque(maxlen=500)    # Decoded messages
        self._spots = deque(maxlen=1000)     # All spots
        self._qso_logged = deque(maxlen=100) # Logged QSOs
        self._status = {}                    # Latest WSJT-X status
        self._wspr_decodes = deque(maxlen=200)  # WSPR spots

        # Statistics
        self._stats = {
            'packets_received': 0,
            'packets_decoded': 0,
            'decode_errors': 0,
            'start_time': None,
            'last_packet': None
        }

        # UDP socket
        self._socket = None

        # Callbacks for new data events
        self._callbacks = {
            'on_decode': [],
            'on_qso_logged': [],
            'on_status': [],
            'on_wspr': []
        }

    def register_callback(self, event, callback):
        """
        Register a callback for a data event.

        Args:
            event: Event name (on_decode, on_qso_logged,
                   on_status, on_wspr)
            callback: Function to call with decoded data
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _trigger_callbacks(self, event, data):
        """
        Trigger all registered callbacks for an event.

        Args:
            event: Event name
            data: Data to pass to callbacks
        """
        for callback in self._callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                print(f"[WSJTX-UDP] Callback error: {e}")

    def start(self):
        """
        Start the UDP listener thread.

        Creates UDP socket and begins receiving packets
        in a background daemon thread.

        Returns:
            bool: True if started successfully
        """
        if self._running:
            return True

        try:
            # Create UDP socket
            self._socket = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM,
                socket.IPPROTO_UDP
            )

            # Allow multiple listeners on same port
            self._socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1
            )

            # Set socket timeout for clean shutdown
            self._socket.settimeout(1.0)

            # Bind to port
            self._socket.bind((self.host, self.port))

            # Join multicast group if configured
            if self.multicast_group:
                import struct
                mreq = struct.pack(
                    '4sL',
                    socket.inet_aton(self.multicast_group),
                    socket.INADDR_ANY
                )
                self._socket.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_ADD_MEMBERSHIP,
                    mreq
                )

            self._running = True
            self._stats['start_time'] = datetime.utcnow().isoformat()

            # Start background thread
            self._thread = threading.Thread(
                target=self._listen_loop,
                daemon=True,
                name='wsjtx-udp-listener'
            )
            self._thread.start()

            print(
                f"[WSJTX-UDP] Listening on "
                f"{self.host}:{self.port}"
            )
            return True

        except OSError as e:
            print(f"[WSJTX-UDP] Socket error: {e}")
            self._running = False
            return False
        except Exception as e:
            print(f"[WSJTX-UDP] Start error: {e}")
            self._running = False
            return False

    def stop(self):
        """
        Stop the UDP listener.

        Signals the listener thread to stop and
        closes the UDP socket.
        """
        self._running = False

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

        print("[WSJTX-UDP] Listener stopped")

    def _listen_loop(self):
        """
        Main UDP receive loop (runs in background thread).

        Continuously receives UDP packets, decodes them,
        and routes to appropriate data structures.
        """
        print("[WSJTX-UDP] Listener thread started")

        while self._running:
            try:
                # Receive UDP packet (max 65535 bytes)
                data, addr = self._socket.recvfrom(65535)

                self._stats['packets_received'] += 1
                self._stats['last_packet'] = (
                    datetime.utcnow().isoformat()
                )

                # Decode packet
                packet = self.decoder.decode(data)

                if packet is None:
                    self._stats['decode_errors'] += 1
                    continue

                self._stats['packets_decoded'] += 1

                # Route to appropriate handler
                self._handle_packet(packet)

            except socket.timeout:
                # Normal - allows checking _running flag
                continue
            except OSError:
                # Socket closed - exit loop
                break
            except Exception as e:
                print(f"[WSJTX-UDP] Receive error: {e}")
                time.sleep(0.1)

        print("[WSJTX-UDP] Listener thread stopped")

    def _handle_packet(self, packet):
        """
        Route decoded packet to appropriate data structure.

        Args:
            packet: Decoded packet dictionary
        """
        msg_type = packet.get('type')

        with self._lock:
            if msg_type == WSJTXPacketDecoder.MSG_STATUS:
                # Update current status
                self._status = packet
                self._trigger_callbacks('on_status', packet)

            elif msg_type == WSJTXPacketDecoder.MSG_DECODE:
                # Add to decode queue
                self._decodes.appendleft(packet)

                # Add to spots if has callsign
                if packet.get('callsign') or packet.get('de_call'):
                    self._spots.appendleft(packet)

                self._trigger_callbacks('on_decode', packet)

            elif msg_type == WSJTXPacketDecoder.MSG_QSO_LOGGED:
                # Add to logged QSO queue
                self._qso_logged.appendleft(packet)
                self._trigger_callbacks('on_qso_logged', packet)

            elif msg_type == WSJTXPacketDecoder.MSG_WSPR_DECODE:
                # Add to WSPR decode queue
                self._wspr_decodes.appendleft(packet)
                self._trigger_callbacks('on_wspr', packet)

            elif msg_type == WSJTXPacketDecoder.MSG_HEARTBEAT:
                # Update status with version info
                if self._status:
                    self._status['heartbeat'] = packet
                else:
                    self._status = packet

            elif msg_type == WSJTXPacketDecoder.MSG_CLOSE:
                # WSJT-X is closing
                self._status['closed'] = True
                print("[WSJTX-UDP] WSJT-X closed")

    def get_decodes(self, limit=50):
        """
        Get recent decoded messages.

        Args:
            limit: Maximum number to return

        Returns:
            list: Recent decoded messages, newest first
        """
        with self._lock:
            return list(self._decodes)[:limit]

    def get_spots(self, limit=100, mode_filter=None):
        """
        Get decoded spots with optional mode filter.

        Args:
            limit: Maximum spots to return
            mode_filter: Filter by mode string (optional)

        Returns:
            list: Spots newest first
        """
        with self._lock:
            spots = list(self._spots)

        if mode_filter:
            spots = [
                s for s in spots
                if s.get('mode', '').upper() ==
                mode_filter.upper()
            ]

        return spots[:limit]

    def get_qso_logged(self):
        """
        Get and clear pending logged QSOs.

        Returns:
            list: Pending QSO log entries
        """
        with self._lock:
            qsos = list(self._qso_logged)
            self._qso_logged.clear()
            return qsos

    def get_wspr_decodes(self, limit=50):
        """
        Get recent WSPR decodes.

        Args:
            limit: Maximum to return

        Returns:
            list: WSPR decodes newest first
        """
        with self._lock:
            return list(self._wspr_decodes)[:limit]

    def get_status(self):
        """
        Get latest WSJT-X status.

        Returns:
            dict: Current WSJT-X status
        """
        with self._lock:
            return dict(self._status)

    def get_stats(self):
        """
        Get listener statistics.

        Returns:
            dict: Packet statistics
        """
        with self._lock:
            stats = dict(self._stats)
            stats['running'] = self._running
            stats['port'] = self.port
            stats['host'] = self.host
            return stats

    def send_command(self, data):
        """
        Send a UDP command to WSJT-X.

        WSJT-X listens on the same port for commands
        from external applications.

        Args:
            data: Bytes to send

        Returns:
            bool: True if sent successfully
        """
        try:
            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM
            )
            # Send to WSJT-X (typically localhost)
            sock.sendto(data, ('localhost', self.port))
            sock.close()
            return True
        except Exception as e:
            print(f"[WSJTX-UDP] Send error: {e}")
            return False

    def clear_spots(self):
        """Clear all spot data."""
        with self._lock:
            self._spots.clear()
            self._decodes.clear()

    def is_connected(self):
        """
        Check if receiving data from WSJT-X.

        Returns:
            bool: True if receiving packets
        """
        if not self._running:
            return False

        # Check if we've received a packet recently
        last = self._stats.get('last_packet')
        if not last:
            return False

        try:
            last_dt = datetime.fromisoformat(last)
            diff = (datetime.utcnow() - last_dt).total_seconds()
            # Consider connected if packet received in last 60 seconds
            return diff < 60
        except Exception:
            return False