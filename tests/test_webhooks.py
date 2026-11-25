from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from curl_sms import CurlSMSError, parse_webhook, verify_webhook
from curl_sms.webhooks import SIGNATURE_HEADER

SECRET = "whsec_test_example_secret"
NOW = 1_763_892_907
BODY = json.dumps(
    {
        "id": "evt_01JDQ8P2K9W3E6Y1M4T7Z0R5C8",
        "type": "sms.status_changed",
        "created": NOW,
        "data": {
            "id": "01JDQ8M3V6R1T5ZK2X9N4C7B0A",
            "status": "delivered",
            "at": "2026-11-23T10:15:07.123Z",
        },
    },
    separators=(",", ":"),
).encode("utf-8")


def sign(body: bytes, timestamp: int = NOW, secret: str = SECRET) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_header_name() -> None:
    assert SIGNATURE_HEADER == "X-CurlSMS-Signature"


def test_valid_signature() -> None:
    assert verify_webhook(SECRET, sign(BODY), BODY, now=NOW)


def test_valid_signature_str_body() -> None:
    assert verify_webhook(SECRET, sign(BODY), BODY.decode("utf-8"), now=NOW + 10)


def test_known_vector() -> None:
    body = b'{"id":"evt_1","type":"webhook.test","created":1700000000,"data":{}}'
    expected = hmac.new(b"whsec_abc", b"1700000000." + body, hashlib.sha256).hexdigest()
    header = f"t=1700000000,v1={expected}"
    assert verify_webhook("whsec_abc", header, body, now=1700000000)
    assert not verify_webhook("abc", header, body, now=1700000000), "prefix is part of the key"


def test_wrong_secret() -> None:
    assert not verify_webhook("whsec_other", sign(BODY), BODY, now=NOW)


def test_tampered_body() -> None:
    tampered = BODY.replace(b"delivered", b"failed")
    assert not verify_webhook(SECRET, sign(BODY), tampered, now=NOW)


def test_expired_timestamp() -> None:
    header = sign(BODY, timestamp=NOW - 301)
    assert not verify_webhook(SECRET, header, BODY, now=NOW)
    assert verify_webhook(SECRET, header, BODY, now=NOW, tolerance=600)


def test_future_timestamp() -> None:
    assert not verify_webhook(SECRET, sign(BODY, timestamp=NOW + 301), BODY, now=NOW)


def test_multiple_signatures() -> None:
    good = sign(BODY).split("v1=")[1]
    header = f"t={NOW},v1={'0' * 64},v1={good}"
    assert verify_webhook(SECRET, header, BODY, now=NOW)


@pytest.mark.parametrize(
    "header",
    [None, "", "garbage", f"t={NOW}", "v1=abc", f"t=abc,v1={'0' * 64}", f"t={NOW},v1=zz"],
)
def test_malformed_headers(header: str | None) -> None:
    assert not verify_webhook(SECRET, header, BODY, now=NOW)


def test_empty_secret() -> None:
    assert not verify_webhook("", sign(BODY, secret=""), BODY, now=NOW)


def test_parse_webhook() -> None:
    event = parse_webhook(SECRET, sign(BODY), BODY, now=NOW)
    assert event["type"] == "sms.status_changed"
    if event["type"] == "sms.status_changed":
        assert event["data"]["status"] == "delivered"


def test_parse_webhook_invalid_signature() -> None:
    with pytest.raises(CurlSMSError) as info:
        parse_webhook("whsec_other", sign(BODY), BODY, now=NOW)
    assert info.value.code == "invalid_signature"
    assert info.value.status is None


def test_parse_webhook_invalid_json() -> None:
    body = b"not json"
    with pytest.raises(CurlSMSError) as info:
        parse_webhook(SECRET, sign(body), body, now=NOW)
    assert info.value.code == "invalid_json"


def test_parse_webhook_not_an_event() -> None:
    body = b"[1, 2, 3]"
    with pytest.raises(CurlSMSError) as info:
        parse_webhook(SECRET, sign(body), body, now=NOW)
    assert info.value.code == "invalid_json"
