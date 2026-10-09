"""Codec autocontido e assinado para requestState."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from .constants import REQUEST_STATE_TTL_SECONDS
from .errors import RequestStateError


def secret_key() -> bytes:
    secret = os.environ.get("REQUEST_STATE_SECRET", "")
    try:
        key = bytes.fromhex(secret)
    except ValueError:
        key = b""
    if len(key) < 32:
        raise SystemExit(
            "REQUEST_STATE_SECRET must be hexadecimal and contain at least 32 bytes"
        )
    return key


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def seal(arguments: dict[str, Any], key: str, alternatives: list[str]) -> str:
    now = int(time.time())
    payload = {
        "v": 1,
        "tool": "reservar_sala",
        "arguments": arguments,
        "key": key,
        "alternatives": alternatives,
        "iat": now,
        "exp": now + REQUEST_STATE_TTL_SECONDS,
    }
    encoded = _encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    signature = _encode(
        hmac.new(secret_key(), f"v1.{encoded}".encode(), hashlib.sha256).digest()
    )
    return f"v1.{encoded}.{signature}"


def unseal(token: str) -> dict[str, Any]:
    try:
        version, encoded, signature = token.split(".")
        if version != "v1":
            raise RequestStateError("requestState invalido")
        expected = _encode(
            hmac.new(
                secret_key(), f"{version}.{encoded}".encode(), hashlib.sha256
            ).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise RequestStateError("requestState invalido")
        raw = base64.urlsafe_b64decode(encoded + "=" * ((4 - len(encoded) % 4) % 4))
        payload = json.loads(raw)
        if (
            payload.get("exp", 0) <= int(time.time())
            or payload.get("tool") != "reservar_sala"
            or payload.get("v") != 1
        ):
            raise RequestStateError("requestState invalido")
        return payload
    except RequestStateError:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RequestStateError("requestState invalido") from exc
