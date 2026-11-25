# curl-sms for Python

[![CI](https://github.com/curl-sms/curl-sms-python/actions/workflows/ci.yml/badge.svg)](https://github.com/curl-sms/curl-sms-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/curl-sms?color=0a0a0a)](https://pypi.org/project/curl-sms/)
[![Python versions](https://img.shields.io/pypi/pyversions/curl-sms?color=0a0a0a)](https://pypi.org/project/curl-sms/)
[![License: MIT](https://img.shields.io/badge/license-MIT-0a0a0a)](LICENSE)

Official Python client for the [curl-sms](https://curl-sms.com) SMS API: send an SMS with one line of Python.

- Zero dependencies, standard library only
- Fully typed (`py.typed`), Python 3.10+
- Safe automatic retries with idempotency keys
- Webhook signature verification built in

## Install

```bash
pip install curl-sms
```

## Quickstart

```python
from curl_sms import CurlSMS

client = CurlSMS("cs_test_example")  # or set CURLSMS_API_KEY

message = client.send("+4915123456789", "Hello from Python")
print(message["id"], message["status"])  # 01JDQ8M3V6R1T5ZK2X9N4C7B0A queued
```

Test keys (`cs_test_…`) run all checks, send nothing and cost nothing. Their
status changes are simulated (`sent`, then `delivered`). Switch to a live key
(`cs_live_…`) when you are ready.

## Configuration

```python
client = CurlSMS(
    api_key="cs_test_example",  # default: env CURLSMS_API_KEY, then CURLSMS_KEY
    base_url="https://curl-sms.com",  # default
    timeout=30,  # seconds per attempt
    max_retries=2,  # retries on network errors, 429 and 5xx
    language="en",  # language of error messages: "en" or "de"
)
```

If no key is passed and none is set in the environment, the constructor raises
`ValueError`. `Client` is an alias of `CurlSMS`.

## Methods

All methods return plain dictionaries with `TypedDict` type hints (`Message`,
`SendManyResponse`, `Estimate`, `ListResponse`, `Account`). Money amounts are
strings in euros, exactly as the API returns them (for example `"0.09"`).

### send

Send one SMS:

```python
message = client.send("+4915123456789", "Your code is 123456")
```

Send the same text to up to 100 receivers:

```python
result = client.send(
    receivers=["+4915123456789", "+4917612345678"],
    body="Server backup finished.",
)
print(result["ids"])
```

Schedule an SMS (at most one year ahead) with a timezone-aware `datetime` or an
RFC 3339 string:

```python
from datetime import datetime, timezone

client.send(
    "+4915123456789",
    "Reminder: maintenance starts in 10 minutes.",
    send_at=datetime(2026, 12, 1, 7, 50, tzinfo=timezone.utc),
)
client.send("+4915123456789", "Good morning", send_at="2026-12-01T08:00:00+01:00")
```

### estimate

Get encoding, number of parts and price without sending. With `receiver`, the
result also says whether the SMS would be allowed right now:

```python
estimate = client.estimate("Grüße aus Brühl 👋", receiver="+4915123456789")
print(estimate["encoding"], estimate["segments"], estimate["price"], estimate["allowed"])
```

### get

```python
message = client.get("01JDQ8M3V6R1T5ZK2X9N4C7B0A")
# scheduled, queued, dispatched, sent, delivered, failed, expired or canceled
print(message["status"])
```

### cancel

Cancel a scheduled or queued SMS (it is refunded). For any other SMS only the
text is deleted:

```python
message = client.cancel("01JDQ8M3V6R1T5ZK2X9N4C7B0A")
```

### list

List SMS ordered by last change, optionally filtered by status. Pass
`next_cursor` back as `since` to poll for changes:

```python
page = client.list(status="delivered", limit=50)
for message in page["data"]:
    print(message["id"], message["status"])

changes = client.list(since=page["next_cursor"])
```

### account

```python
account = client.account()
print(account["plan"], account["included_left"], account["balance"])
```

### health

Does not send the API key, so it works with any key:

```python
print(client.health())  # {'ok': True, 'version': '1.0.0'}
```

## Error handling

Every failure raises `CurlSMSError`:

```python
from curl_sms import CurlSMS, CurlSMSError

client = CurlSMS("cs_test_example")

try:
    client.send(receivers=["+4915123456789", "12345"], body="Hello")
except CurlSMSError as err:
    print(err.status)  # 422
    print(err.code)  # "invalid_receiver"
    print(err.message)  # "Invalid receiver number."
    print(err.index)  # 1, the failing entry in receivers
    print(err.error_id)  # set for "internal" errors; quote it to support
    print(err.retry_after)  # seconds from Retry-After, if sent
```

`code` is one of the API error codes (see the
[API reference](https://curl-sms.com/docs/api)) or one of these client-side
codes:

| Code | Meaning |
|---|---|
| `network_error` | The API could not be reached. |
| `timeout` | No response within `timeout` seconds. |
| `invalid_response` | The response was not a valid API response. |
| `invalid_signature` | A webhook signature was missing, wrong or expired (`parse_webhook`). |

Invalid arguments (for example both `receiver` and `receivers`) raise
`ValueError` or `TypeError` before any request is made.

## Retries and idempotency

Requests are retried up to `max_retries` times (default 2) on network errors,
timeouts, `429` and `5xx`, with exponential backoff (0.5 s, 1 s, 2 s, …). A
`Retry-After` header is honored, capped at 30 seconds. Other `4xx` errors are
never retried.

`send` always sends an `Idempotency-Key` header. If you do not pass one, a
random UUID is generated and reused for every retry of that call, so a retry
never sends the SMS twice. Pass your own key to make sends idempotent across
processes too, for example per order:

```python
client.send("+4915123456789", "Your order has shipped.", idempotency_key="order-4711-shipped")
```

The same key and request within 24 hours returns the stored response.

## Webhooks

curl-sms signs every webhook request with the `X-CurlSMS-Signature` header.
Verify it against the raw request body with your endpoint secret (`whsec_…`):

```python
import os

from flask import Flask, abort, request

from curl_sms import CurlSMSError, parse_webhook

app = Flask(__name__)
WEBHOOK_SECRET = os.environ["CURLSMS_WEBHOOK_SECRET"]


@app.post("/webhooks/curl-sms")
def curl_sms_webhook():
    try:
        event = parse_webhook(
            WEBHOOK_SECRET,
            request.headers.get("X-CurlSMS-Signature"),
            request.get_data(),  # raw bytes, before JSON parsing
        )
    except CurlSMSError:
        abort(400)

    if event["type"] == "sms.status_changed":
        data = event["data"]
        print(data["id"], data["status"])
    return "", 204
```

`verify_webhook(secret, signature_header, raw_body)` returns `True` or `False`
if you only need the check. Timestamps older than 300 seconds are rejected
(`tolerance=` to change). Delivery is at-least-once: deduplicate on the event
`id` (also sent as `X-CurlSMS-Event-Id`).

## Examples

See [`examples/`](examples/) for runnable scripts.

## Links

- Website: <https://curl-sms.com>
- Documentation: <https://curl-sms.com/docs>
- API reference: <https://curl-sms.com/docs/api>
- Pricing: <https://curl-sms.com/pricing>
- Support: <help@curl-sms.com>
- More SDKs and tools: <https://github.com/curl-sms>

## License

[MIT](LICENSE)
