"""
Secret Key Manager
==================
Handles automatic generation and persistence of Flask SECRET_KEY.
Generates a secure random key on first run and stores it persistently.
"""

import os
import secrets
from pathlib import Path

class SecretKeyManager:
    """
    Manages Flask SECRET_KEY with automatic generation and persistence.
    
    The secret key is stored in a file and reused across container restarts.
    If no key exists, a new cryptographically secure key is generated.
    """
    
    def __init__(self, key_file_path=None):
        """
        Initialize the secret key manager.
        
        Args:
            key_file_path: Path to store the secret key file.
                          Defaults to /data/secret_key or ./data/secret_key
        """
        if key_file_path is None:
            # Try Docker path first, fall back to local
            if os.path.exists('/data'):
                key_file_path = '/data/secret_key'
            else:
                # Local development path
                local_data = os.path.join(os.path.dirname(__file__), 'data')
                os.makedirs(local_data, exist_ok=True)
                key_file_path = os.path.join(local_data, 'secret_key')
        
        self.key_file_path = key_file_path
        self._ensure_directory_exists()
    
    def _ensure_directory_exists(self):
        """Ensure the directory for the key file exists."""
        key_dir = os.path.dirname(self.key_file_path)
        if key_dir and not os.path.exists(key_dir):
            try:
                os.makedirs(key_dir, mode=0o755, exist_ok=True)
                print(f"Created directory for secret key: {key_dir}")
            except Exception as e:
                print(f"Warning: Could not create directory {key_dir}: {e}")
    
    def _generate_key(self):
        """
        Generate a cryptographically secure random key.
        
        Returns:
            str: 64-character hexadecimal string (256 bits of entropy)
        """
        return secrets.token_hex(32)  # 32 bytes = 256 bits
    
    def _read_key(self):
        """
        Read the secret key from file.
        
        Returns:
            str: The secret key, or None if file doesn't exist or can't be read
        """
        try:
            if os.path.exists(self.key_file_path):
                with open(self.key_file_path, 'r') as f:
                    key = f.read().strip()
                    if key and len(key) >= 32:  # Minimum key length
                        print(f"✓ Loaded existing secret key from {self.key_file_path}")
                        return key
                    else:
                        print(f"Warning: Invalid key in {self.key_file_path}, will regenerate")
                        return None
        except Exception as e:
            print(f"Warning: Could not read secret key from {self.key_file_path}: {e}")
        
        return None
    
    def _write_key(self, key):
        """
        Write the secret key to file with secure permissions.
        
        Args:
            key: The secret key to write
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Write key to file
            with open(self.key_file_path, 'w') as f:
                f.write(key)
            
            # Set secure permissions (owner read/write only)
            os.chmod(self.key_file_path, 0o600)
            
            print(f"✓ Secret key saved to {self.key_file_path}")
            return True
        except Exception as e:
            print(f"ERROR: Could not write secret key to {self.key_file_path}: {e}")
            return False
    
    def get_or_create_key(self):
        """
        Get existing secret key or create a new one.
        
        This is the main method to use. It will:
        1. Try to read an existing key from file
        2. If no key exists, generate a new one and save it
        3. Return the key
        
        Returns:
            str: The secret key
        """
        # Try to read existing key
        key = self._read_key()
        
        if key:
            return key
        
        # Generate new key
        print("Generating new secret key...")
        key = self._generate_key()
        
        # Try to save it
        if self._write_key(key):
            print("✓ New secret key generated and saved")
        else:
            print("Warning: Secret key generated but could not be saved")
            print("         Key will be regenerated on next restart")
        
        return key
    
    def regenerate_key(self):
        """
        Force regeneration of the secret key.
        
        WARNING: This will invalidate all existing sessions!
        
        Returns:
            str: The new secret key
        """
        print("Regenerating secret key (this will invalidate all sessions)...")
        key = self._generate_key()
        self._write_key(key)
        return key
    
    def validate_key(self, key):
        """
        Validate that a key meets minimum security requirements.
        
        Args:
            key: The key to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if not key:
            return False, "Key is empty"
        
        if len(key) < 32:
            return False, "Key is too short (minimum 32 characters)"
        
        # Check if it's a known insecure default
        insecure_defaults = [
            'dev-secret-key-change-in-production',
            'change-this-in-production',
            'secret',
            'password',
            'changeme'
        ]
        
        if key.lower() in insecure_defaults:
            return False, "Key is a known insecure default"
        
        return True, ""


# Global instance for easy access
_secret_key_manager = None

def get_secret_key():
    """
    Get or create the application secret key.
    
    This is a convenience function that uses a global instance.
    
    Returns:
        str: The secret key
    """
    global _secret_key_manager
    
    if _secret_key_manager is None:
        _secret_key_manager = SecretKeyManager()
    
    return _secret_key_manager.get_or_create_key()
