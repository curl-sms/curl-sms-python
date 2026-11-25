from __future__ import annotations

import socket
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import curl_sms
from conftest import MESSAGE, MockServer
from curl_sms import Client, CurlSMS, CurlSMSError

# ----------------------------------------------------------------- basics


def test_version_and_alias() -> None:
    assert curl_sms.__version__ == "1.0.0"
    assert Client is CurlSMS


def test_api_key_from_argument_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURLSMS_API_KEY", "cs_test_from_env")
    assert CurlSMS("cs_test_example").api_key == "cs_test_example"


def test_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURLSMS_API_KEY", "cs_test_primary")
    monkeypatch.setenv("CURLSMS_KEY", "cs_test_fallback")
    assert CurlSMS().api_key == "cs_test_primary"


def test_api_key_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CURLSMS_API_KEY", raising=False)
    monkeypatch.setenv("CURLSMS_KEY", "cs_test_fallback")
    assert CurlSMS().api_key == "cs_test_fallback"


def test_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CURLSMS_API_KEY", raising=False)
    monkeypatch.delenv("CURLSMS_KEY", raising=False)
    with pytest.raises(ValueError, match="CURLSMS_API_KEY"):
        CurlSMS()


def test_invalid_options() -> None:
    with pytest.raises(ValueError, match="timeout"):
        CurlSMS("cs_test_example", timeout=0)
    with pytest.raises(ValueError, match="max_retries"):
        CurlSMS("cs_test_example", max_retries=-1)


# ----------------------------------------------------------- success paths


def test_send_single(server: MockServer, client: CurlSMS) -> None:
    server.respond(202, MESSAGE)
    message = client.send("+4915123456789", "Hello")

    assert message == MESSAGE
    req = server.requests[0]
    assert req.method == "POST"
    assert req.path == "/api/sms/send"
    assert req.json() == {"receiver": "+4915123456789", "body": "Hello"}
    assert req.headers["authorization"] == "Bearer cs_test_example"
    assert req.headers["content-type"] == "application/json"
    assert req.headers["accept"] == "application/json"
    assert req.headers["accept-language"] == "en"
    assert req.headers["user-agent"] == f"curl-sms-python/{curl_sms.__version__}"
    assert uuid.UUID(req.headers["idempotency-key"]).version == 4


def test_send_unicode_body(server: MockServer, client: CurlSMS) -> None:
    server.respond(202, MESSAGE)
    client.send("+4915123456789", "Grüße 👋")
    assert server.requests[0].json()["body"] == "Grüße 👋"


def test_send_many(server: MockServer, client: CurlSMS) -> None:
    second = {**MESSAGE, "id": "01JDQ8M3V6R1T5ZK2X9N4C7B0B", "receiver": "+4917612345678"}
    server.respond(202, {"ids": [MESSAGE["id"], second["id"]], "messages": [MESSAGE, second]})

    result = client.send(receivers=("+4915123456789", "+4917612345678"), body="Backup done.")

    assert result["ids"] == [MESSAGE["id"], second["id"]]
    assert len(result["messages"]) == 2
    assert server.requests[0].json() == {
        "receivers": ["+4915123456789", "+4917612345678"],
        "body": "Backup done.",
    }


def test_send_with_datetime_and_custom_key(server: MockServer, client: CurlSMS) -> None:
    server.respond(202, {**MESSAGE, "status": "scheduled"})
    when = datetime(2026, 12, 1, 8, 0, tzinfo=timezone(timedelta(hours=1)))

    client.send("+4915123456789", "Later", send_at=when, idempotency_key="order-42")

    req = server.requests[0]
    assert req.json()["send_at"] == "2026-12-01T08:00:00+01:00"
    assert req.headers["idempotency-key"] == "order-42"


def test_send_with_string_send_at(server: MockServer, client: CurlSMS) -> None:
    server.respond(202, MESSAGE)
    client.send("+4915123456789", "Later", send_at="2026-12-01T07:00:00Z")
    assert server.requests[0].json()["send_at"] == "2026-12-01T07:00:00Z"


def test_send_argument_validation(client: CurlSMS) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        client.send(body="x")  # type: ignore[call-overload]
    with pytest.raises(ValueError, match="exactly one"):
        client.send("+4915123456789", "x", receivers=["+4915123456789"])  # type: ignore[call-overload]
    with pytest.raises(TypeError):
        client.send(receivers="+4915123456789", body="x")
    with pytest.raises(ValueError, match="empty"):
        client.send(receivers=[], body="x")
    with pytest.raises(ValueError, match="timezone-aware"):
        client.send("+4915123456789", "x", send_at=datetime(2026, 12, 1, 8, 0))


def test_estimate(server: MockServer, client: CurlSMS) -> None:
    server.respond(200, {"encoding": "ucs2", "segments": 1, "price": "0.00", "allowed": True})
    result = client.estimate("Grüße 👋", receiver="+4915123456789")
    assert result["encoding"] == "ucs2"
    assert result["price"] == "0.00"
    req = server.requests[0]
    assert req.path == "/api/sms/estimate"
    assert req.json() == {"body": "Grüße 👋", "receiver": "+4915123456789"}
    assert "idempotency-key" not in req.headers


def test_get_url_encodes_id(server: MockServer, client: CurlSMS) -> None:
    server.respond(200, MESSAGE)
    assert client.get("a/b c")["id"] == MESSAGE["id"]
    req = server.requests[0]
    assert req.method == "GET"
    assert req.path == "/api/sms/a%2Fb%20c"


def test_get_empty_id(client: CurlSMS) -> None:
    with pytest.raises(ValueError, match="id"):
        client.get("")


def test_cancel(server: MockServer, client: CurlSMS) -> None:
    server.respond(200, {**MESSAGE, "status": "canceled", "refunded": True})
    result = client.cancel(MESSAGE["id"])
    assert result["status"] == "canceled"
    assert server.requests[0].method == "DELETE"
    assert server.requests[0].path == f"/api/sms/{MESSAGE['id']}"


def test_list_with_filters(server: MockServer, client: CurlSMS) -> None:
    server.respond(200, {"data": [MESSAGE], "next_cursor": "c2"})
    page = client.list(since="c1", status="delivered", limit=50)
    assert page["next_cursor"] == "c2"
    assert page["data"][0]["id"] == MESSAGE["id"]
    req = server.requests[0]
    assert req.path == "/api/sms"
    assert req.query == {"since": ["c1"], "status": ["delivered"], "limit": ["50"]}


def test_list_without_filters(server: MockServer, client: CurlSMS) -> None:
    server.respond(200, {"data": [], "next_cursor": "c1"})
    client.list()
    assert server.requests[0].query == {}


def test_account(server: MockServer, client: CurlSMS) -> None:
    account = {
        "plan": "paid",
        "mode": "test",
        "included_total": 300,
        "included_left": 287,
        "balance": "12.40",
        "spend_limit": "10.00",
        "spent": "0.18",
        "daily_limit": 500,
        "daily_left": 488,
    }
    server.respond(200, account)
    assert client.account() == account
    assert server.requests[0].path == "/api/account"


def test_health_without_auth(server: MockServer, client: CurlSMS) -> None:
    server.respond(200, {"ok": True, "version": "1.0.0"})
    assert client.health() == {"ok": True, "version": "1.0.0"}
    assert "authorization" not in server.requests[0].headers


def test_health_unhealthy_returns_body(
    server: MockServer, client: CurlSMS, sleeps: list[float]
) -> None:
    for _ in range(3):
        server.respond(503, {"ok": False, "version": "1.0.0"})
    assert client.health() == {"ok": False, "version": "1.0.0"}
    assert sleeps == [0.5, 1.0]


def test_language_header(server: MockServer) -> None:
    server.respond(200, {"data": [], "next_cursor": "c"})
    CurlSMS("cs_test_example", base_url=server.url + "/", language="de").list()
    assert server.requests[0].headers["accept-language"] == "de"
    assert server.requests[0].path == "/api/sms"


# ------------------------------------------------------------ error mapping


def test_validation_error_with_index(server: MockServer, client: CurlSMS) -> None:
    server.error(422, "invalid_receiver", "Invalid receiver number.", index=1)
    with pytest.raises(CurlSMSError) as info:
        client.send(receivers=["+4915123456789", "123"], body="x")
    err = info.value
    assert err.status == 422
    assert err.code == "invalid_receiver"
    assert err.message == "Invalid receiver number."
    assert err.index == 1
    assert err.error_id is None
    assert "invalid_receiver" in str(err)
    assert "Invalid receiver number." in str(err)


def test_internal_error_id(server: MockServer, sleeps: list[float]) -> None:
    c = CurlSMS("cs_test_example", base_url=server.url, max_retries=0)
    server.error(500, "internal", "Internal error.", error_id="01JDQ8R0A1B2C3D4E5F6G7H8J9")
    with pytest.raises(CurlSMSError) as info:
        c.account()
    assert info.value.status == 500
    assert info.value.code == "internal"
    assert info.value.error_id == "01JDQ8R0A1B2C3D4E5F6G7H8J9"
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "unauthorized"),
        (402, "insufficient_balance"),
        (403, "verification_required"),
        (404, "not_found"),
        (409, "not_cancelable"),
    ],
)
def test_client_errors_map_code(
    server: MockServer, client: CurlSMS, sleeps: list[float], status: int, code: str
) -> None:
    server.error(status, code)
    with pytest.raises(CurlSMSError) as info:
        client.cancel("01JDQ8M3V6R1T5ZK2X9N4C7B0A")
    assert (info.value.status, info.value.code) == (status, code)
    assert len(server.requests) == 1
    assert sleeps == []


def test_non_json_error_body(server: MockServer, client: CurlSMS) -> None:
    server.respond(400, raw=b"<html>Bad Request</html>")
    with pytest.raises(CurlSMSError) as info:
        client.account()
    assert info.value.code == "invalid_response"
    assert info.value.status == 400


def test_non_json_success_body(server: MockServer, client: CurlSMS) -> None:
    server.respond(200, raw=b"not json")
    with pytest.raises(CurlSMSError) as info:
        client.account()
    assert info.value.code == "invalid_response"
    assert info.value.status == 200


# ------------------------------------------------------------------ retries


def test_retry_on_429_respects_retry_after(
    server: MockServer, client: CurlSMS, sleeps: list[float]
) -> None:
    server.error(429, "rate_limited", headers={"Retry-After": "2"})
    server.respond(202, MESSAGE)

    assert client.send("+4915123456789", "Hello")["id"] == MESSAGE["id"]
    assert sleeps == [2.0]
    assert len(server.requests) == 2
    keys = {r.headers["idempotency-key"] for r in server.requests}
    assert len(keys) == 1, "idempotency key must be stable across retries"


def test_retry_after_is_capped(server: MockServer, client: CurlSMS, sleeps: list[float]) -> None:
    server.error(429, "rate_limited", headers={"Retry-After": "120"})
    server.respond(200, {"data": [], "next_cursor": "c"})
    client.list()
    assert sleeps == [30.0]


def test_retry_on_503_with_backoff(
    server: MockServer, client: CurlSMS, sleeps: list[float]
) -> None:
    server.error(503, "internal")
    server.error(503, "internal")
    server.respond(202, MESSAGE)
    client.send("+4915123456789", "Hello", idempotency_key="fixed-key")
    assert sleeps == [0.5, 1.0]
    assert [r.headers["idempotency-key"] for r in server.requests] == ["fixed-key"] * 3


def test_retry_on_503_with_retry_after(
    server: MockServer, client: CurlSMS, sleeps: list[float]
) -> None:
    server.error(503, "internal", headers={"Retry-After": "3"})
    server.respond(200, MESSAGE)
    client.get(MESSAGE["id"])
    assert sleeps == [3.0]


def test_retries_exhausted(server: MockServer, client: CurlSMS, sleeps: list[float]) -> None:
    for _ in range(3):
        server.error(429, "rate_limited", "Too many requests.", headers={"Retry-After": "1"})
    with pytest.raises(CurlSMSError) as info:
        client.account()
    assert info.value.code == "rate_limited"
    assert info.value.status == 429
    assert info.value.retry_after == 1.0
    assert len(server.requests) == 3
    assert sleeps == [1.0, 1.0]


def test_no_retry_on_422(server: MockServer, client: CurlSMS, sleeps: list[float]) -> None:
    server.error(422, "body_empty")
    server.respond(202, MESSAGE)
    with pytest.raises(CurlSMSError) as info:
        client.send("+4915123456789", "")
    assert info.value.code == "body_empty"
    assert len(server.requests) == 1
    assert sleeps == []


def test_max_retries_zero(server: MockServer, sleeps: list[float]) -> None:
    c = CurlSMS("cs_test_example", base_url=server.url, max_retries=0)
    c._sleep = sleeps.append
    server.error(503, "internal")
    with pytest.raises(CurlSMSError):
        c.account()
    assert len(server.requests) == 1
    assert sleeps == []


def test_network_error_is_retried(sleeps: list[float]) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    c = CurlSMS("cs_test_example", base_url=f"http://127.0.0.1:{port}", max_retries=1)
    c._sleep = sleeps.append
    with pytest.raises(CurlSMSError) as info:
        c.account()
    assert info.value.code == "network_error"
    assert info.value.status is None
    assert sleeps == [0.5]


def test_timeout(server: MockServer) -> None:
    c = CurlSMS("cs_test_example", base_url=server.url, timeout=0.2, max_retries=0)
    server.respond(200, {"ok": True, "version": "1"}, delay=1.0)
    with pytest.raises(CurlSMSError) as info:
        c.health()
    assert info.value.code == "timeout"
    assert info.value.status is None
