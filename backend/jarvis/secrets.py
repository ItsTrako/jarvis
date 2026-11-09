"""Almacenamiento seguro de credenciales.

Usa el Administrador de credenciales de Windows (DPAPI, cifrado por usuario) mediante
``keyring``. Los valores nunca se escriben en ficheros del proyecto ni en los logs.
Como alternativa (p. ej. CI) se aceptan variables de entorno.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets as _pysecrets

import keyring
from keyring.errors import KeyringError

SERVICE = "JARVIS-Assistant"

# nombre lógico -> variable de entorno alternativa
KNOWN_SECRETS: dict[str, str] = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "telegram_bot_token": "JARVIS_TELEGRAM_TOKEN",
    "elevenlabs_api_key": "ELEVENLABS_API_KEY",
    "azure_speech_key": "AZURE_SPEECH_KEY",
    "telegram_pin_hash": "",
}


def get_secret(name: str) -> str | None:
    env = KNOWN_SECRETS.get(name)
    if env and os.environ.get(env):
        return os.environ[env]
    try:
        return keyring.get_password(SERVICE, name)
    except KeyringError:
        return None


def set_secret(name: str, value: str) -> None:
    if name not in KNOWN_SECRETS:
        raise ValueError(f"Secreto desconocido: {name}")
    value = value.strip()
    if not value:
        raise ValueError("Valor vacío")
    keyring.set_password(SERVICE, name, value)


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except KeyringError:
        pass


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def secrets_status() -> dict[str, bool]:
    return {k: has_secret(k) for k in KNOWN_SECRETS}


# ---------------------------------------------------------------- PIN (Telegram)

def set_pin(pin: str) -> None:
    pin = pin.strip()
    if not (pin.isdigit() and 4 <= len(pin) <= 12):
        raise ValueError("El PIN debe tener entre 4 y 12 dígitos")
    salt = _pysecrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()
    set_secret("telegram_pin_hash", f"{salt}${digest}")


def verify_pin(pin: str) -> bool:
    stored = get_secret("telegram_pin_hash")
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", pin.strip().encode(), bytes.fromhex(salt), 200_000).hex()
    return hmac.compare_digest(candidate, digest)


def mask(value: str | None) -> str:
    if not value:
        return ""
    return value[:4] + "…" + value[-4:] if len(value) > 12 else "••••"
