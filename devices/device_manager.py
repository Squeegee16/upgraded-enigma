"""
Device Manager
===============
Centralized device ownership and access management.

Tracks which plugin currently holds exclusive access
to each hardware device (SDR, GPS, Radio) and provides:
    - Exclusive device assignment to plugins
    - Warning generation when a plugin tries to use
      a device already claimed by another plugin
    - Release mechanism when navigating away
    - Dashboard status showing which plugin owns what

Device Model:
    Each physical device can only be actively used
    by one plugin at a time. The RTL-SDR, for example,
    cannot be shared between the Morse plugin and the
    P25Survey plugin simultaneously.

    Plugins CLAIM a device when they start using it.
    Plugins RELEASE a device when they stop.
    The dashboard always has READ access for status.
"""

import threading
from datetime import datetime


class DeviceManager:
    """
    Manages exclusive device access across all plugins.

    Stores which plugin currently owns each device and
    provides claim/release/warning functionality.
    """

    # Device names that can be managed
    MANAGED_DEVICES = ['sdr', 'radio', 'gps']

    def __init__(self):
        """Initialise with no devices claimed."""
        self._lock = threading.Lock()

        # Current owner of each device
        # Format: {device_name: plugin_name or None}
        self._owners = {
            'sdr': None,
            'radio': None,
            'gps': None,
        }

        # Claim timestamps
        self._claimed_at = {
            'sdr': None,
            'radio': None,
            'gps': None,
        }

        # Claim history for logging
        self._history = []
        self._max_history = 100

    def claim(self, device_name, plugin_name):
        """
        Claim exclusive access to a device for a plugin.

        If the device is already claimed by another plugin
        this method returns False with a warning message.
        Plugins should check the return value and warn
        the user before proceeding.

        Args:
            device_name: 'sdr', 'radio', or 'gps'
            plugin_name: Name of the requesting plugin

        Returns:
            tuple: (success: bool, message: str)
        """
        if device_name not in self.MANAGED_DEVICES:
            return True, f"{device_name} is not managed"

        with self._lock:
            current_owner = self._owners.get(device_name)

            # Already owned by this plugin
            if current_owner == plugin_name:
                return True, f"Already claimed by {plugin_name}"

            # Claimed by a different plugin
            if current_owner is not None:
                msg = (
                    f"{device_name.upper()} is currently "
                    f"in use by the {current_owner} plugin. "
                    f"Please disconnect it from {current_owner} "
                    f"before using it here."
                )
                return False, msg

            # Claim the device
            self._owners[device_name] = plugin_name
            self._claimed_at[device_name] = (
                datetime.utcnow().isoformat()
            )

            self._add_history(
                'claim', device_name, plugin_name
            )

            return (
                True,
                f"{device_name.upper()} claimed by "
                f"{plugin_name}"
            )

    def release(self, device_name, plugin_name):
        """
        Release a device claimed by a plugin.

        Only the current owner can release a device.
        An admin release (plugin_name=None) forces release.

        Args:
            device_name: Device to release
            plugin_name: Plugin releasing the device
                         (None = force release)

        Returns:
            tuple: (success: bool, message: str)
        """
        if device_name not in self.MANAGED_DEVICES:
            return True, "Not a managed device"

        with self._lock:
            current_owner = self._owners.get(device_name)

            if current_owner is None:
                return True, "Device not claimed"

            # Only owner or admin (None) can release
            if (plugin_name is not None and
                    current_owner != plugin_name):
                return (
                    False,
                    f"Cannot release {device_name}: "
                    f"owned by {current_owner}"
                )

            self._owners[device_name] = None
            self._claimed_at[device_name] = None

            self._add_history(
                'release', device_name,
                plugin_name or 'admin'
            )

            return (
                True,
                f"{device_name.upper()} released"
            )

    def release_all(self, plugin_name):
        """
        Release all devices claimed by a plugin.

        Called when a plugin page is navigated away from
        or when the plugin is shut down.

        Args:
            plugin_name: Plugin releasing its devices
        """
        released = []
        with self._lock:
            for device in self.MANAGED_DEVICES:
                if self._owners.get(device) == plugin_name:
                    self._owners[device] = None
                    self._claimed_at[device] = None
                    released.append(device)
                    self._add_history(
                        'release_all', device, plugin_name
                    )

        return released

    def get_owner(self, device_name):
        """
        Get the current owner of a device.

        Args:
            device_name: Device to check

        Returns:
            str or None: Plugin name or None if unclaimed
        """
        with self._lock:
            return self._owners.get(device_name)

    def is_available(self, device_name):
        """
        Check if a device is available (unclaimed).

        Args:
            device_name: Device to check

        Returns:
            bool: True if device is not claimed
        """
        with self._lock:
            return self._owners.get(device_name) is None

    def get_status(self):
        """
        Get the ownership status of all managed devices.

        Returns:
            dict: Device name -> owner info dict
        """
        with self._lock:
            return {
                device: {
                    'owner': self._owners[device],
                    'available': (
                        self._owners[device] is None
                    ),
                    'claimed_at': self._claimed_at[device],
                }
                for device in self.MANAGED_DEVICES
            }

    def get_plugin_devices(self, plugin_name):
        """
        Get all devices currently claimed by a plugin.

        Args:
            plugin_name: Plugin to check

        Returns:
            list: Device names owned by the plugin
        """
        with self._lock:
            return [
                device
                for device in self.MANAGED_DEVICES
                if self._owners.get(device) == plugin_name
            ]

    def check_availability(self, device_names,
                           plugin_name):
        """
        Check availability of multiple devices.

        Returns warnings for any devices already in use
        by other plugins.

        Args:
            device_names: List of device names to check
            plugin_name: Plugin requesting access

        Returns:
            dict: {device: warning_or_None}
        """
        results = {}
        with self._lock:
            for device in device_names:
                owner = self._owners.get(device)
                if owner is None or owner == plugin_name:
                    results[device] = None
                else:
                    results[device] = (
                        f"{device.upper()} is in use "
                        f"by {owner} plugin"
                    )
        return results

    def _add_history(self, action, device, plugin):
        """Add entry to claim history."""
        self._history.append({
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'device': device,
            'plugin': plugin,
        })
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_history(self, limit=20):
        """Get recent device claim history."""
        return list(reversed(self._history[-limit:]))


# ------------------------------------------------------------------
# Global device manager instance
# Registered in app.extensions by create_app()
# ------------------------------------------------------------------
_device_manager_instance = None


def get_device_manager():
    """
    Get the global DeviceManager instance.

    Returns:
        DeviceManager: The singleton instance
    """
    global _device_manager_instance
    if _device_manager_instance is None:
        _device_manager_instance = DeviceManager()
    return _device_manager_instance
