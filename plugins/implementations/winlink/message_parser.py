"""
Winlink Message Parser
=======================
Parses Winlink/B2F format messages for display and processing.

Winlink uses the B2F (BBS B2 Forwarding) protocol for messages.
Messages are stored in a specific directory structure by Pat.

Pat message directory structure:
    ~/.local/share/pat/mailbox/
        <callsign>/
            in/          <- Received messages
            out/         <- Outgoing messages
            sent/        <- Sent messages
            archive/     <- Archived messages

Message format:
    Standard email format with additional Winlink headers.
    Body encoding: UTF-8 or Latin-1

Reference:
    https://github.com/la5nta/pat/wiki
    https://winlink.org/B2F
"""

import os
import email
import re
from datetime import datetime
from pathlib import Path


class WinlinkMessageParser:
    """
    Parses and manages Winlink messages stored by Pat.

    Reads messages from the Pat mailbox directory structure
    and provides a unified interface for the plugin UI.
    """

    def __init__(self, mailbox_dir):
        """
        Initialize parser with mailbox directory.

        Args:
            mailbox_dir: Path to Pat mailbox directory
                        (~/.local/share/pat/mailbox/<callsign>/)
        """
        self.mailbox_dir = mailbox_dir

    def get_inbox(self):
        """
        Get all messages from inbox.

        Returns:
            list: Parsed message dictionaries, newest first
        """
        return self._get_messages_from_folder('in')

    def get_outbox(self):
        """
        Get all queued outgoing messages.

        Returns:
            list: Parsed message dictionaries
        """
        return self._get_messages_from_folder('out')

    def get_sent(self):
        """
        Get all sent messages.

        Returns:
            list: Parsed message dictionaries, newest first
        """
        return self._get_messages_from_folder('sent')

    def _get_messages_from_folder(self, folder):
        """
        Get messages from a specific mailbox folder.

        Args:
            folder: Folder name (in, out, sent, archive)

        Returns:
            list: Parsed message dictionaries
        """
        folder_path = os.path.join(self.mailbox_dir, folder)
        messages = []

        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            return messages

        try:
            for filename in sorted(
                os.listdir(folder_path),
                key=lambda x: os.path.getmtime(
                    os.path.join(folder_path, x)
                ),
                reverse=True
            ):
                # Process .b2f and .txt message files
                if filename.endswith(('.b2f', '.txt', '.msg')):
                    filepath = os.path.join(folder_path, filename)
                    msg = self._parse_message(filepath)
                    if msg:
                        msg['folder'] = folder
                        messages.append(msg)

        except Exception as e:
            print(f"[WinlinkParser] Error reading {folder}: {e}")

        return messages

    def _parse_message(self, filepath):
        """
        Parse a single message file.

        Handles both standard email format and B2F format.

        Args:
            filepath: Path to message file

        Returns:
            dict: Parsed message data or None on error
        """
        try:
            with open(filepath, 'r', encoding='utf-8',
                      errors='replace') as f:
                content = f.read()

            # Get file metadata
            stat = os.stat(filepath)
            file_time = datetime.fromtimestamp(stat.st_mtime)

            # Try parsing as RFC 2822 email format
            msg_data = self._parse_email_format(content, filepath)

            if not msg_data:
                # Fall back to simple line-by-line parsing
                msg_data = self._parse_simple_format(content, filepath)

            # Add common fields
            msg_data.update({
                'id': os.path.basename(filepath),
                'filepath': filepath,
                'file_time': file_time.isoformat(),
                'size': stat.st_size
            })

            return msg_data

        except Exception as e:
            print(f"[WinlinkParser] Error parsing {filepath}: {e}")
            return None

    def _parse_email_format(self, content, filepath):
        """
        Parse message in RFC 2822 email format.

        Args:
            content: Message content string
            filepath: Source filepath

        Returns:
            dict: Parsed message or None if not email format
        """
        try:
            msg = email.message_from_string(content)

            # Check if we got valid email headers
            if not msg.get('From') and not msg.get('To'):
                return None

            # Extract body
            body = ''
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode('utf-8', errors='replace')
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode('utf-8', errors='replace')
                else:
                    body = str(msg.get_payload())

            # Parse date
            date_str = msg.get('Date', '')
            parsed_date = self._parse_date(date_str)

            return {
                'from': self._clean_address(msg.get('From', '')),
                'to': self._clean_address(msg.get('To', '')),
                'subject': msg.get('Subject', '(No Subject)'),
                'date': parsed_date,
                'body': body.strip(),
                'message_id': msg.get('Message-ID', ''),
                'format': 'email'
            }

        except Exception:
            return None

    def _parse_simple_format(self, content, filepath):
        """
        Parse message using simple line-by-line header parsing.

        Fallback for non-standard message formats.

        Args:
            content: Message content string
            filepath: Source filepath

        Returns:
            dict: Parsed message data
        """
        lines = content.split('\n')
        headers = {}
        body_lines = []
        in_body = False

        for line in lines:
            if not in_body:
                if line.strip() == '':
                    in_body = True
                    continue

                # Parse header lines
                if ':' in line:
                    key, _, value = line.partition(':')
                    headers[key.strip().lower()] = value.strip()
            else:
                body_lines.append(line)

        return {
            'from': self._clean_address(headers.get('from', '')),
            'to': self._clean_address(headers.get('to', '')),
            'subject': headers.get('subject', '(No Subject)'),
            'date': self._parse_date(headers.get('date', '')),
            'body': '\n'.join(body_lines).strip(),
            'message_id': headers.get('message-id', ''),
            'format': 'simple'
        }

    def _clean_address(self, address):
        """
        Clean and normalize an email/Winlink address.

        Handles formats like:
        - "W1ABC <W1ABC@winlink.org>"
        - "W1ABC@winlink.org"
        - "W1ABC"

        Args:
            address: Raw address string

        Returns:
            str: Cleaned address
        """
        if not address:
            return ''

        # Extract from angle brackets if present
        match = re.search(r'<(.+?)>', address)
        if match:
            return match.group(1).strip()

        return address.strip()

    def _parse_date(self, date_str):
        """
        Parse various date formats to ISO string.

        Args:
            date_str: Date string in various formats

        Returns:
            str: ISO format datetime string or current time
        """
        if not date_str:
            return datetime.utcnow().isoformat()

        # Common formats to try
        formats = [
            '%a, %d %b %Y %H:%M:%S %z',
            '%d %b %Y %H:%M:%S %z',
            '%Y-%m-%d %H:%M:%S',
            '%Y%m%d %H%M%S',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.isoformat()
            except ValueError:
                continue

        return datetime.utcnow().isoformat()

    def create_message_file(self, outbox_dir, from_callsign,
                            to_address, subject, body):
        """
        Create a new outgoing message file.

        Creates a properly formatted Winlink message
        in the Pat outbox directory.

        Args:
            outbox_dir: Path to outbox directory
            from_callsign: Sender callsign
            to_address: Recipient address
            subject: Message subject
            body: Message body text

        Returns:
            tuple: (success, filepath or error message)
        """
        os.makedirs(outbox_dir, exist_ok=True)

        try:
            # Generate unique message ID
            timestamp = datetime.utcnow()
            msg_id = f"{from_callsign}_{timestamp.strftime('%Y%m%d%H%M%S')}"
            filename = f"{msg_id}.txt"
            filepath = os.path.join(outbox_dir, filename)

            # Format as RFC 2822 email
            message_content = (
                f"From: {from_callsign}@winlink.org\r\n"
                f"To: {to_address}\r\n"
                f"Subject: {subject}\r\n"
                f"Date: {timestamp.strftime('%a, %d %b %Y %H:%M:%S +0000')}\r\n"
                f"Message-ID: <{msg_id}@winlink.org>\r\n"
                f"MIME-Version: 1.0\r\n"
                f"Content-Type: text/plain; charset=UTF-8\r\n"
                f"\r\n"
                f"{body}\r\n"
            )

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(message_content)

            return True, filepath

        except Exception as e:
            return False, str(e)

    def get_message_count(self):
        """
        Get message counts for all folders.

        Returns:
            dict: Count for each folder
        """
        counts = {}
        for folder in ['in', 'out', 'sent', 'archive']:
            folder_path = os.path.join(self.mailbox_dir, folder)
            if os.path.exists(folder_path):
                counts[folder] = len([
                    f for f in os.listdir(folder_path)
                    if f.endswith(('.b2f', '.txt', '.msg'))
                ])
            else:
                counts[folder] = 0
        return counts