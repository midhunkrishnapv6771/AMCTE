"""
encryption_engine.py — Cryptographic Vault for Secure Credentials
===============================================================
Handles AES-256 encryption and decryption of pooled credentials using Fernet.
Derives keys using PBKDF2HMAC with SHA-256 and a constant salt.
"""

import base64
import logging
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet

logger = logging.getLogger("encryption_engine")

# Constant salt for key derivation to ensure deterministic keys from the master key
_SALT = b"amtce_secure_credentials_salt_v1"

def _derive_key(passphrase: str) -> bytes:
    """Derives a url-safe 32-byte key from the passphrase using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=100_000
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))

def encrypt_data(plain_text: str, passphrase: str) -> str:
    """Encrypts plain text and returns a base64 encoded cipher text."""
    if not passphrase:
        raise ValueError("Master encryption key is not set.")
    key = _derive_key(passphrase)
    fernet = Fernet(key)
    return fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")

def decrypt_data(cipher_text: str, passphrase: str) -> str:
    """Decrypts cipher text and returns the plain text string."""
    if not passphrase:
        raise ValueError("Master encryption key is not set.")
    key = _derive_key(passphrase)
    fernet = Fernet(key)
    return fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
