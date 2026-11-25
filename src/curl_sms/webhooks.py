"""Verify and parse curl-sms webhook requests.

Every webhook request carries an ``X-CurlSMS-Signature`` header of the form
``t=<unix seconds>,v1=<hex>``. ``v1`` is the hex HMAC-SHA256 of
``<t>.<raw body>``, keyed with the full endpoint secret (including the
``whsec_`` prefix). Always verify against the raw request body, before any
JSON parsing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import cast

from ._errors import CurlSMSError
from .types import WebhookEvent

__all__ = [
    "DEFAULT_TOLERANCE",
    "EVENT_ID_HEADER",
    "SIGNATURE_HEADER",
    "parse_webhook",
    "verify_webhook",
]

SIGNATURE_HEADER = "X-CurlSMS-Signature"
EVENT_ID_HEADER = "X-CurlSMS-Event-Id"
DEFAULT_TOLERANCE = 300


def verify_webhook(
    secret: str,
    signature_header: str | None,
    raw_body: bytes | str,
    tolerance: float = DEFAULT_TOLERANCE,
    now: float | None = None,
) -> bool:
    """Return ``True`` if the signature header is valid for this body.

    Args:
        secret: Endpoint secret from the dashboard (``whsec_...``).
        signature_header: Value of the ``X-CurlSMS-Signature`` header.
        raw_body: The unmodified request body.
        tolerance: Maximum age (and clock skew) of the timestamp in seconds.
        now: Current time as Unix seconds; defaults to ``time.time()``.
    """
    if not secret or not signature_header:
        return False

    timestamp: str | None = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep:
            continue
        if key == "t":
            timestamp = value.strip()
        elif key == "v1":
            signatures.append(value.strip().lower())
    if timestamp is None or not signatures:
        return False
    try:
        signed_at = int(timestamp)
    except ValueError:
        return False

    current = time.time() if now is None else now
    if abs(current - signed_at) > tolerance:
        return False

    body = raw_body.encode("utf-8") if isinstance(raw_body, str) else bytes(raw_body)
    expected = hmac.new(
        secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256
    ).hexdigest()
    expected_bytes = expected.encode("ascii")
    valid = False
    for signature in signatures:
        # Check every candidate so timing does not depend on which one matched.
        if hmac.compare_digest(expected_bytes, signature.encode("utf-8", "replace")):
            valid = True
    return valid


def parse_webhook(
    secret: str,
    signature_header: str | None,
    raw_body: bytes | str,
    tolerance: float = DEFAULT_TOLERANCE,
    now: float | None = None,
) -> WebhookEvent:
    """Verify a webhook request and return the parsed event.

    Raises:
        CurlSMSError: ``code="invalid_signature"`` if the signature is missing,
            wrong or too old; ``code="invalid_json"`` if the body is not a
            webhook event.
    """
    if not verify_webhook(secret, signature_header, raw_body, tolerance=tolerance, now=now):
        raise CurlSMSError(
            "Webhook signature is missing, invalid or expired.", code="invalid_signature"
        )
    try:
        event = json.loads(raw_body)
    except ValueError as exc:
        raise CurlSMSError("Webhook body is not valid JSON.", code="invalid_json") from exc
    if (
        not isinstance(event, dict)
        or not isinstance(event.get("id"), str)
        or not isinstance(event.get("type"), str)
        or not isinstance(event.get("data"), dict)
    ):
        raise CurlSMSError("Webhook body is not a curl-sms event.", code="invalid_json")
    return cast(WebhookEvent, event)
