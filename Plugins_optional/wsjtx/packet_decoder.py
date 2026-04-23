"""
WSJT-X UDP Packet Decoder
==========================
Decodes WSJT-X UDP protocol messages (NetworkMessage.hpp).

WSJT-X sends status updates and decoded messages to
external applications via UDP multicast on port 2237.

Packet Format:
    All packets start with a 4-byte magic number,
    followed by a 4-byte schema version, then a 4-byte
    message type identifier.

Magic Number: 0xADBCCBDA (big-endian)
Schema Version: 2 (current)

Message Types:
    0  - Heartbeat
    1  - Status
    2  - Decode
    3  - Clear
    4  - Reply
    5  - QSO Logged
    6  - Close
    7  - Replay
    8  - Halt TX
    9  - Free Text
    10 - WSPR Decode
    11 - Location
    12 - Logged ADIF
    13 - Highlight Callsign
    14 - Switch Configuration
    15 - Configure

Reference:
    https://github.com/WSJTX/wsjtx/blob/master/Network/NetworkMessage.hpp
"""

import struct
from datetime import datetime, date, time


class WSJTXPacketDecoder:
    """
    Decodes binary WSJT-X UDP network messages.

    Handles all WSJT-X message types and returns
    structured Python dictionaries for each decoded packet.
    """

    # Magic number identifying WSJT-X packets
    MAGIC = 0xADBCCBDA

    # Message type constants matching NetworkMessage.hpp
    MSG_HEARTBEAT = 0
    MSG_STATUS = 1
    MSG_DECODE = 2
    MSG_CLEAR = 3
    MSG_REPLY = 4
    MSG_QSO_LOGGED = 5
    MSG_CLOSE = 6
    MSG_REPLAY = 7
    MSG_HALT_TX = 8
    MSG_FREE_TEXT = 9
    MSG_WSPR_DECODE = 10
    MSG_LOCATION = 11
    MSG_LOGGED_ADIF = 12
    MSG_HIGHLIGHT_CALLSIGN = 13
    MSG_SWITCH_CONFIG = 14
    MSG_CONFIGURE = 15

    # Human-readable type names
    TYPE_NAMES = {
        0: 'Heartbeat',
        1: 'Status',
        2: 'Decode',
        3: 'Clear',
        4: 'Reply',
        5: 'QSO Logged',
        6: 'Close',
        7: 'Replay',
        8: 'Halt TX',
        9: 'Free Text',
        10: 'WSPR Decode',
        11: 'Location',
        12: 'Logged ADIF',
    }

    def __init__(self):
        """Initialize decoder with offset tracking."""
        self._data = b''
        self._offset = 0

    def decode(self, data):
        """
        Decode a raw WSJT-X UDP packet.

        Validates the magic number, reads the schema
        version and message type, then dispatches to
        the appropriate type decoder.

        Args:
            data: Raw bytes from UDP socket

        Returns:
            dict: Decoded packet data or None if invalid
        """
        if len(data) < 12:
            return None

        self._data = data
        self._offset = 0

        try:
            # Read and validate magic number (4 bytes, big-endian)
            magic = self._read_uint32()
            if magic != self.MAGIC:
                return None

            # Read schema version
            schema = self._read_uint32()

            # Read message type
            msg_type = self._read_uint32()

            # Read client ID (unique identifier for WSJT-X instance)
            client_id = self._read_utf8()

            # Build base packet info
            packet = {
                'type': msg_type,
                'type_name': self.TYPE_NAMES.get(
                    msg_type, f'Unknown({msg_type})'
                ),
                'schema': schema,
                'client_id': client_id,
                'timestamp': datetime.utcnow().isoformat()
            }

            # Dispatch to type-specific decoder
            if msg_type == self.MSG_HEARTBEAT:
                packet.update(self._decode_heartbeat())
            elif msg_type == self.MSG_STATUS:
                packet.update(self._decode_status())
            elif msg_type == self.MSG_DECODE:
                packet.update(self._decode_decode())
            elif msg_type == self.MSG_QSO_LOGGED:
                packet.update(self._decode_qso_logged())
            elif msg_type == self.MSG_CLOSE:
                packet.update({'action': 'close'})
            elif msg_type == self.MSG_WSPR_DECODE:
                packet.update(self._decode_wspr_decode())
            elif msg_type == self.MSG_LOGGED_ADIF:
                packet.update(self._decode_logged_adif())

            return packet

        except Exception as e:
            print(f"[WSJTX-Decoder] Decode error: {e}")
            return None

    def _read_uint32(self):
        """
        Read a 4-byte unsigned integer (big-endian).

        Returns:
            int: Unsigned 32-bit integer
        """
        value = struct.unpack_from('>I', self._data, self._offset)[0]
        self._offset += 4
        return value

    def _read_int32(self):
        """
        Read a 4-byte signed integer (big-endian).

        Returns:
            int: Signed 32-bit integer
        """
        value = struct.unpack_from('>i', self._data, self._offset)[0]
        self._offset += 4
        return value

    def _read_uint64(self):
        """
        Read an 8-byte unsigned integer (big-endian).

        Returns:
            int: Unsigned 64-bit integer
        """
        value = struct.unpack_from('>Q', self._data, self._offset)[0]
        self._offset += 8
        return value

    def _read_uint8(self):
        """
        Read a single byte.

        Returns:
            int: Byte value
        """
        value = struct.unpack_from('>B', self._data, self._offset)[0]
        self._offset += 1
        return value

    def _read_bool(self):
        """
        Read a boolean value (1 byte).

        Returns:
            bool: Boolean value
        """
        return bool(self._read_uint8())

    def _read_double(self):
        """
        Read an 8-byte double precision float.

        Returns:
            float: Double precision float
        """
        value = struct.unpack_from('>d', self._data, self._offset)[0]
        self._offset += 8
        return value

    def _read_utf8(self):
        """
        Read a UTF-8 string prefixed with 4-byte length.

        WSJT-X strings are length-prefixed. A length of
        0xFFFFFFFF indicates a null/empty string.

        Returns:
            str: Decoded string or empty string
        """
        length = self._read_uint32()

        # 0xFFFFFFFF indicates null string in WSJT-X protocol
        if length == 0xFFFFFFFF or length == 0:
            return ''

        if self._offset + length > len(self._data):
            return ''

        value = self._data[
            self._offset:self._offset + length
        ].decode('utf-8', errors='replace')

        self._offset += length
        return value

    def _read_datetime(self):
        """
        Read a WSJT-X datetime value.

        WSJT-X encodes dates as Julian day numbers (uint64)
        and times as milliseconds since midnight (uint32).

        Returns:
            str: ISO format datetime string
        """
        try:
            # Julian day number
            julian_day = self._read_uint64()

            # Milliseconds since midnight
            ms_since_midnight = self._read_uint32()

            # Timezone offset indicator
            timespec = self._read_uint8()

            # Convert Julian day to Python date
            # Julian Day Number to calendar date
            j = julian_day + 32044
            g = j // 146097
            dg = j % 146097
            c = (dg // 36524 + 1) * 3 // 4
            dc = dg - c * 36524
            b = dc // 1461
            db = dc % 1461
            a = (db // 365 + 1) * 3 // 4
            da = db - a * 365
            y = g * 400 + c * 100 + b * 4 + a
            m = (da * 5 + 308) // 153 - 2
            d = da - (m + 4) * 153 // 5 + 122
            year = y - 4800 + (m + 2) // 12
            month = (m + 2) % 12 + 1
            day = d + 1

            # Convert ms to time
            total_seconds = ms_since_midnight // 1000
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            dt = datetime(
                year, month, day, hours, minutes, seconds
            )
            return dt.isoformat()

        except Exception:
            return datetime.utcnow().isoformat()

    def _decode_heartbeat(self):
        """
        Decode heartbeat message (type 0).

        Sent periodically by WSJT-X to indicate it is
        still running. Contains max schema and version info.

        Returns:
            dict: Heartbeat data
        """
        try:
            max_schema = self._read_uint32()
            version = self._read_utf8()
            revision = self._read_utf8()

            return {
                'max_schema': max_schema,
                'version': version,
                'revision': revision
            }
        except Exception:
            return {}

    def _decode_status(self):
        """
        Decode status message (type 1).

        Sent when WSJT-X state changes including frequency,
        mode, callsign, grid, and TX/RX state.

        Returns:
            dict: Complete WSJT-X status data
        """
        try:
            dial_freq = self._read_uint64()       # Dial frequency Hz
            mode = self._read_utf8()              # Mode (FT8, WSPR, etc)
            dx_call = self._read_utf8()           # DX callsign
            report = self._read_utf8()            # Signal report
            tx_mode = self._read_utf8()           # TX mode
            tx_enabled = self._read_bool()        # TX enabled
            transmitting = self._read_bool()      # Currently transmitting
            decoding = self._read_bool()          # Currently decoding
            rx_df = self._read_uint32()           # RX audio frequency
            tx_df = self._read_uint32()           # TX audio frequency
            de_call = self._read_utf8()           # My callsign
            de_grid = self._read_utf8()           # My grid
            dx_grid = self._read_utf8()           # DX grid
            tx_watchdog = self._read_bool()       # TX watchdog
            sub_mode = self._read_utf8()          # Sub-mode
            fast_mode = self._read_bool()         # Fast mode
            special_op_mode = self._read_uint8()  # Special operation

            return {
                'dial_frequency': dial_freq,
                'dial_frequency_mhz': dial_freq / 1_000_000,
                'mode': mode,
                'dx_call': dx_call,
                'report': report,
                'tx_mode': tx_mode,
                'tx_enabled': tx_enabled,
                'transmitting': transmitting,
                'decoding': decoding,
                'rx_df': rx_df,
                'tx_df': tx_df,
                'de_call': de_call,
                'de_grid': de_grid,
                'dx_grid': dx_grid,
                'tx_watchdog': tx_watchdog,
                'sub_mode': sub_mode,
                'fast_mode': fast_mode,
                'special_op_mode': special_op_mode
            }
        except Exception as e:
            print(f"[WSJTX-Decoder] Status decode error: {e}")
            return {}

    def _decode_decode(self):
        """
        Decode a received message (type 2).

        Sent when WSJT-X successfully decodes a received
        transmission. Contains the decoded message text,
        signal quality, and timing.

        Returns:
            dict: Decoded message data
        """
        try:
            new_decode = self._read_bool()     # New (vs replay)
            decode_time = self._read_datetime()  # UTC time
            snr = self._read_int32()            # Signal-to-noise dB
            delta_time = self._read_double()    # Time offset seconds
            delta_freq = self._read_uint32()    # Freq offset Hz
            mode = self._read_utf8()            # Mode string
            message = self._read_utf8()         # Decoded message text
            low_confidence = self._read_bool()  # Low confidence flag
            off_air = self._read_bool()         # Off-air decode

            # Parse callsigns from FT8/FT4/JT65 message
            parsed = self._parse_message(message)

            return {
                'new_decode': new_decode,
                'decode_time': decode_time,
                'snr': snr,
                'delta_time': round(delta_time, 1),
                'delta_freq': delta_freq,
                'mode': mode,
                'message': message,
                'low_confidence': low_confidence,
                'off_air': off_air,
                'callsign': parsed.get('callsign', ''),
                'grid': parsed.get('grid', ''),
                'is_cq': parsed.get('is_cq', False),
                'de_call': parsed.get('de_call', ''),
                'dx_call': parsed.get('dx_call', ''),
            }
        except Exception as e:
            print(f"[WSJTX-Decoder] Decode error: {e}")
            return {}

    def _decode_qso_logged(self):
        """
        Decode QSO logged message (type 5).

        Sent by WSJT-X when a QSO is logged via the
        internal log window. Contains complete contact data.

        Returns:
            dict: Logged QSO data
        """
        try:
            date_time_off = self._read_datetime()  # QSO end time
            dx_call = self._read_utf8()            # DX callsign
            dx_grid = self._read_utf8()            # DX grid
            tx_freq = self._read_uint64()          # TX frequency Hz
            mode = self._read_utf8()               # Mode
            rst_sent = self._read_utf8()           # RST sent
            rst_rcvd = self._read_utf8()           # RST received
            tx_power = self._read_utf8()           # TX power
            comments = self._read_utf8()           # Comments
            name = self._read_utf8()               # Contact name
            date_time_on = self._read_datetime()   # QSO start time
            op_call = self._read_utf8()            # Operator callsign
            my_call = self._read_utf8()            # Station callsign
            my_grid = self._read_utf8()            # Station grid
            exchange_sent = self._read_utf8()      # Exchange sent
            exchange_rcvd = self._read_utf8()      # Exchange received

            return {
                'date_time_off': date_time_off,
                'date_time_on': date_time_on,
                'dx_call': dx_call,
                'dx_grid': dx_grid,
                'tx_frequency': tx_freq,
                'tx_frequency_mhz': tx_freq / 1_000_000,
                'mode': mode,
                'rst_sent': rst_sent,
                'rst_rcvd': rst_rcvd,
                'tx_power': tx_power,
                'comments': comments,
                'name': name,
                'op_call': op_call,
                'my_call': my_call,
                'my_grid': my_grid,
                'exchange_sent': exchange_sent,
                'exchange_rcvd': exchange_rcvd
            }
        except Exception as e:
            print(f"[WSJTX-Decoder] QSO logged error: {e}")
            return {}

    def _decode_wspr_decode(self):
        """
        Decode WSPR decode message (type 10).

        WSPR (Weak Signal Propagation Reporter) decodes
        contain callsign, grid, and power level.

        Returns:
            dict: WSPR decode data
        """
        try:
            new_decode = self._read_bool()
            decode_time = self._read_datetime()
            snr = self._read_int32()
            delta_time = self._read_double()
            frequency = self._read_uint64()
            drift = self._read_int32()
            callsign = self._read_utf8()
            grid = self._read_utf8()
            power = self._read_int32()
            off_air = self._read_bool()

            return {
                'new_decode': new_decode,
                'decode_time': decode_time,
                'snr': snr,
                'delta_time': round(delta_time, 1),
                'frequency': frequency,
                'frequency_mhz': frequency / 1_000_000,
                'drift': drift,
                'callsign': callsign,
                'grid': grid,
                'power': power,
                'off_air': off_air,
                'is_wspr': True
            }
        except Exception as e:
            print(f"[WSJTX-Decoder] WSPR error: {e}")
            return {}

    def _decode_logged_adif(self):
        """
        Decode logged ADIF message (type 12).

        Contains complete ADIF formatted log entry sent
        by WSJT-X when a QSO is logged.

        Returns:
            dict: ADIF log data
        """
        try:
            adif_text = self._read_utf8()
            return {
                'adif': adif_text,
                'parsed': self._parse_adif(adif_text)
            }
        except Exception:
            return {}

    def _parse_message(self, message):
        """
        Parse callsigns and grid from WSJT-X decoded messages.

        WSJT-X messages follow these common formats:
            CQ DE_CALL GRID       - CQ call with grid
            DE_CALL DX_CALL GRID  - Call/reply with grid
            DE_CALL DX_CALL R-XX  - Contact report
            DE_CALL DX_CALL RRR   - Contact confirmation
            DE_CALL DX_CALL 73    - QSO complete

        Args:
            message: Decoded message text string

        Returns:
            dict: Parsed message components
        """
        result = {
            'is_cq': False,
            'callsign': '',
            'de_call': '',
            'dx_call': '',
            'grid': '',
            'report': ''
        }

        if not message:
            return result

        parts = message.strip().split()

        if not parts:
            return result

        # Maidenhead grid locator pattern (4 or 6 chars)
        import re
        grid_pattern = re.compile(
            r'^[A-R]{2}[0-9]{2}([A-X]{2})?$',
            re.IGNORECASE
        )

        # CQ message: "CQ DE_CALL GRID" or "CQ ZONE DE_CALL GRID"
        if parts[0] == 'CQ':
            result['is_cq'] = True
            if len(parts) >= 3:
                result['de_call'] = parts[-2]
                result['callsign'] = parts[-2]
                # Check if last part is a grid
                if grid_pattern.match(parts[-1]):
                    result['grid'] = parts[-1]

        # Standard message: "DE_CALL DX_CALL ..."
        elif len(parts) >= 2:
            result['de_call'] = parts[0]
            result['callsign'] = parts[0]
            result['dx_call'] = parts[1]

            # Check for grid in third position
            if len(parts) >= 3 and grid_pattern.match(parts[2]):
                result['grid'] = parts[2]

            # Check for report
            if len(parts) >= 3 and not grid_pattern.match(parts[2]):
                result['report'] = parts[2]

        return result

    def _parse_adif(self, adif_text):
        """
        Parse ADIF formatted text into a dictionary.

        ADIF fields are formatted as: <FIELDNAME:length>value

        Args:
            adif_text: ADIF formatted string

        Returns:
            dict: Parsed ADIF fields
        """
        import re
        fields = {}

        pattern = re.compile(r'<(\w+):(\d+)>([^<]*)')
        matches = pattern.findall(adif_text)

        for field_name, length, value in matches:
            fields[field_name.upper()] = value[:int(length)]

        return fields

    def encode_reply(self, client_id, decode_packet):
        """
        Encode a Reply message to reply to a decode.

        Used to direct WSJT-X to reply to a specific
        decoded station.

        Args:
            client_id: WSJT-X client identifier string
            decode_packet: Previously decoded packet dict

        Returns:
            bytes: Encoded reply message
        """
        try:
            buf = bytearray()

            # Magic number
            buf.extend(struct.pack('>I', self.MAGIC))

            # Schema version
            buf.extend(struct.pack('>I', 2))

            # Message type: Reply (4)
            buf.extend(struct.pack('>I', self.MSG_REPLY))

            # Client ID
            self._write_utf8(buf, client_id)

            # Time (from decode packet)
            # Simplified: use current time
            # In production, extract from decode_packet
            self._write_utf8(buf, decode_packet.get('message', ''))

            return bytes(buf)

        except Exception as e:
            print(f"[WSJTX-Decoder] Reply encode error: {e}")
            return None

    def encode_halt_tx(self, client_id, auto_tx_only=False):
        """
        Encode a Halt TX command message.

        Instructs WSJT-X to stop transmitting.

        Args:
            client_id: WSJT-X client identifier
            auto_tx_only: Only halt auto-TX sequences

        Returns:
            bytes: Encoded halt TX message
        """
        buf = bytearray()
        buf.extend(struct.pack('>I', self.MAGIC))
        buf.extend(struct.pack('>I', 2))
        buf.extend(struct.pack('>I', self.MSG_HALT_TX))
        self._write_utf8(buf, client_id)
        buf.extend(struct.pack('>B', int(auto_tx_only)))
        return bytes(buf)

    def encode_free_text(self, client_id, text, send=False):
        """
        Encode a Free Text message command.

        Sets the free text field in WSJT-X and
        optionally initiates transmission.

        Args:
            client_id: WSJT-X client identifier
            text: Free text to set (max 13 chars)
            send: If True, start transmitting

        Returns:
            bytes: Encoded free text message
        """
        buf = bytearray()
        buf.extend(struct.pack('>I', self.MAGIC))
        buf.extend(struct.pack('>I', 2))
        buf.extend(struct.pack('>I', self.MSG_FREE_TEXT))
        self._write_utf8(buf, client_id)
        self._write_utf8(buf, text[:13])  # Max 13 chars
        buf.extend(struct.pack('>B', int(send)))
        return bytes(buf)

    @staticmethod
    def _write_utf8(buf, text):
        """
        Write a length-prefixed UTF-8 string to buffer.

        Args:
            buf: bytearray to write to
            text: String to encode
        """
        if not text:
            buf.extend(struct.pack('>I', 0xFFFFFFFF))
        else:
            encoded = text.encode('utf-8')
            buf.extend(struct.pack('>I', len(encoded)))
            buf.extend(encoded)