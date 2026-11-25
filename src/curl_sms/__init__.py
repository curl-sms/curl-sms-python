"""Official Python client for the curl-sms SMS API.

>>> from curl_sms import CurlSMS
>>> client = CurlSMS("cs_test_example")  # doctest: +SKIP
>>> client.send("+4915123456789", "Hello from Python")  # doctest: +SKIP
"""

from ._client import DEFAULT_BASE_URL, Client, CurlSMS
from ._errors import CurlSMSError
from ._version import __version__
from .types import (
    Account,
    Encoding,
    ErrorCode,
    Estimate,
    HealthResponse,
    ListResponse,
    Message,
    Mode,
    SendManyResponse,
    Status,
    WebhookEvent,
    WebhookEventType,
)
from .webhooks import parse_webhook, verify_webhook

__all__ = [
    "DEFAULT_BASE_URL",
    "Account",
    "Client",
    "CurlSMS",
    "CurlSMSError",
    "Encoding",
    "ErrorCode",
    "Estimate",
    "HealthResponse",
    "ListResponse",
    "Message",
    "Mode",
    "SendManyResponse",
    "Status",
    "WebhookEvent",
    "WebhookEventType",
    "__version__",
    "parse_webhook",
    "verify_webhook",
]
