"""Stockage chiffré des identifiants du robot.

Sur Windows on utilise DPAPI (lié à la session utilisateur), ce qui évite de stocker
une clé à côté du secret. Ailleurs, repli sur un fichier de clé en 0600 + Fernet.
Rien n'est jamais renvoyé au navigateur : l'API n'expose que `configure: true/false`.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
from pathlib import Path

from .config import SECRET_PATH, ensure_dirs


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _DataBlob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in = _blob(data)
    blob_out = _DataBlob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    args = (
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ) if protect else (
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not fn(*args):
        raise OSError("DPAPI a refusé l'opération")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _fernet():
    from cryptography.fernet import Fernet

    key_path = SECRET_PATH.with_suffix(".key")
    if key_path.exists():
        key = key_path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
    return Fernet(key)


def save_credentials(blid: str, password: str, host: str) -> None:
    ensure_dirs()
    payload = json.dumps({"blid": blid, "password": password, "host": host}).encode()
    if sys.platform == "win32":
        wrapped = _dpapi(payload, protect=True)
        SECRET_PATH.write_bytes(b"DPAPI1" + wrapped)
    else:
        SECRET_PATH.write_bytes(b"FERNET1" + _fernet().encrypt(payload))
    try:
        os.chmod(SECRET_PATH, 0o600)
    except OSError:
        pass


def load_credentials() -> dict[str, str] | None:
    if not SECRET_PATH.exists():
        return None
    raw = SECRET_PATH.read_bytes()
    try:
        if raw.startswith(b"DPAPI1"):
            data = _dpapi(raw[6:], protect=False)
        elif raw.startswith(b"FERNET1"):
            data = _fernet().decrypt(raw[7:])
        else:
            return None
        return json.loads(data.decode())
    except Exception:
        return None


def clear_credentials() -> bool:
    if SECRET_PATH.exists():
        SECRET_PATH.unlink()
        return True
    return False


def has_credentials() -> bool:
    return load_credentials() is not None
