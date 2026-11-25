"""HTTP client for the curl-sms API."""

from __future__ import annotations

import http.client
import json
import math
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from email.message import Message as _HeaderMap
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping, Sequence, Tuple, cast, overload

from ._errors import CurlSMSError
from ._version import __version__
from .types import (
    Account,
    Estimate,
    HealthResponse,
    ListResponse,
    Message,
    SendManyResponse,
    Status,
)

__all__ = ["DEFAULT_BASE_URL", "Client", "CurlSMS"]

DEFAULT_BASE_URL = "https://curl-sms.com"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
MAX_RETRY_AFTER = 30.0
_INITIAL_BACKOFF = 0.5
_USER_AGENT = f"curl-sms-python/{__version__}"

_RawResponse = Tuple[int, Mapping[str, str], bytes]


class CurlSMS:
    """Client for the curl-sms SMS API.

    Args:
        api_key: API key (``cs_live_...`` or ``cs_test_...``). Defaults to the
            ``CURLSMS_API_KEY`` environment variable, then ``CURLSMS_KEY``.
        base_url: API origin. Defaults to ``https://curl-sms.com``.
        timeout: Timeout per HTTP attempt in seconds.
        max_retries: How often a failed request is retried (network errors,
            429 and 5xx). ``0`` disables retries.
        language: Language of API error messages (``"en"`` or ``"de"``).

    Raises:
        ValueError: If no API key is given or found in the environment, or an
            option is out of range.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        language: str = "en",
    ) -> None:
        key = api_key or os.environ.get("CURLSMS_API_KEY") or os.environ.get("CURLSMS_KEY")
        if not key:
            raise ValueError(
                "No curl-sms API key: pass api_key=... or set the CURLSMS_API_KEY "
                "environment variable. Create a key at https://curl-sms.com/docs."
            )
        if timeout <= 0:
            raise ValueError("timeout must be greater than 0")
        if max_retries < 0:
            raise ValueError("max_retries must be 0 or greater")
        self.api_key: str = key
        self.base_url: str = base_url.rstrip("/")
        self.timeout: float = float(timeout)
        self.max_retries: int = int(max_retries)
        self.language: str = language
        self._opener = urllib.request.build_opener()
        self._sleep: Callable[[float], None] = time.sleep

    def __repr__(self) -> str:
        return f"CurlSMS(base_url={self.base_url!r})"

    # ------------------------------------------------------------------ SMS

    @overload
    def send(
        self,
        receiver: str,
        body: str,
        *,
        send_at: datetime | str | None = None,
        idempotency_key: str | None = None,
    ) -> Message: ...

    @overload
    def send(
        self,
        *,
        receivers: Sequence[str],
        body: str,
        send_at: datetime | str | None = None,
        idempotency_key: str | None = None,
    ) -> SendManyResponse: ...

    def send(
        self,
        receiver: str | None = None,
        body: str | None = None,
        *,
        receivers: Sequence[str] | None = None,
        send_at: datetime | str | None = None,
        idempotency_key: str | None = None,
    ) -> Message | SendManyResponse:
        """Send an SMS to one receiver or the same text to up to 100 receivers.

        Pass exactly one of ``receiver`` or ``receivers``. Returns a ``Message``
        for ``receiver`` and a ``SendManyResponse`` for ``receivers``.

        ``send_at`` schedules the SMS; it takes a timezone-aware ``datetime`` or
        an RFC 3339 string. An idempotency key (UUID4) is generated if none is
        given, so automatic retries never send twice.
        """
        if (receiver is None) == (receivers is None):
            raise ValueError("Pass exactly one of receiver or receivers.")
        if body is None:
            raise ValueError("body is required.")
        payload: dict[str, Any] = {}
        if receiver is not None:
            payload["receiver"] = receiver
        else:
            if isinstance(receivers, str):
                raise TypeError("receivers must be a sequence of strings, not a string.")
            receiver_list = [str(r) for r in cast("Sequence[str]", receivers)]
            if not receiver_list:
                raise ValueError("receivers must not be empty.")
            payload["receivers"] = receiver_list
        payload["body"] = body
        if send_at is not None:
            payload["send_at"] = _format_send_at(send_at)
        key = idempotency_key if idempotency_key is not None else str(uuid.uuid4())
        result = self._request(
            "POST", "/api/sms/send", body=payload, idempotency_key=key, retry=True
        )
        if receiver is not None:
            return cast(Message, result)
        return cast(SendManyResponse, result)

    def estimate(self, body: str, receiver: str | None = None) -> Estimate:
        """Calculate encoding, parts and price of a text without sending it.

        With ``receiver``, the result also says whether the SMS would be allowed
        right now (``allowed``) and, if not, why (``code``).
        """
        payload: dict[str, Any] = {"body": body}
        if receiver is not None:
            payload["receiver"] = receiver
        return cast(Estimate, self._request("POST", "/api/sms/estimate", body=payload))

    def get(self, id: str) -> Message:
        """Get an SMS by its ID."""
        return cast(Message, self._request("GET", _sms_path(id)))

    def cancel(self, id: str) -> Message:
        """Cancel a scheduled or queued SMS (refunded), or delete the text of any other SMS."""
        return cast(Message, self._request("DELETE", _sms_path(id)))

    def list(
        self,
        since: str | None = None,
        status: Status | None = None,
        limit: int | None = None,
    ) -> ListResponse:
        """List SMS ordered by last change.

        Pass ``next_cursor`` of the previous page as ``since`` to get only what
        changed afterwards. ``limit`` is the page size (1-500, default 100).
        """
        query: dict[str, str] = {}
        if since is not None:
            query["since"] = since
        if status is not None:
            query["status"] = status
        if limit is not None:
            query["limit"] = str(int(limit))
        return cast(ListResponse, self._request("GET", "/api/sms", query=query))

    # -------------------------------------------------------------- account

    def account(self) -> Account:
        """Get plan, included SMS, balance and limits."""
        return cast(Account, self._request("GET", "/api/account"))

    def health(self) -> HealthResponse:
        """Check whether the API is up.

        Returns ``{"ok": False, ...}`` instead of raising when the API reports
        itself unhealthy (HTTP 503) and retries are used up.
        """
        return cast(
            HealthResponse,
            self._request("GET", "/api/health", auth=False, accept_status=(503,)),
        )

    # ------------------------------------------------------------- internals

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        auth: bool = True,
        retry: bool = True,
        accept_status: tuple[int, ...] = (),
    ) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "Accept": "application/json",
            "Accept-Language": self.language,
            "User-Agent": _USER_AGENT,
        }
        if auth:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        # POST /api/sms/send is only safe to repeat with an idempotency key.
        can_retry = retry and (path != "/api/sms/send" or idempotency_key is not None)

        attempt = 0
        while True:
            try:
                status, resp_headers, raw = self._send_once(method, url, headers, data)
            except CurlSMSError:
                if can_retry and attempt < self.max_retries:
                    self._sleep(_backoff(attempt))
                    attempt += 1
                    continue
                raise

            if 200 <= status < 300:
                return _decode_json(status, raw)

            error = _error_from_response(status, resp_headers, raw)
            if can_retry and attempt < self.max_retries and (status == 429 or status >= 500):
                if error.retry_after is not None:
                    delay = min(error.retry_after, MAX_RETRY_AFTER)
                else:
                    delay = _backoff(attempt)
                self._sleep(delay)
                attempt += 1
                continue

            if status in accept_status:
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except ValueError:
                    payload = None
                if isinstance(payload, dict):
                    return payload
            raise error

    def _send_once(
        self, method: str, url: str, headers: Mapping[str, str], data: bytes | None
    ) -> _RawResponse:
        request = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return response.status, _header_map(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except (OSError, http.client.HTTPException):
                raw = b""
            finally:
                exc.close()
            return exc.code, _header_map(exc.headers), raw
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise _timeout_error(self.timeout) from exc
            raise CurlSMSError(
                f"Could not reach {self.base_url}: {exc.reason}", code="network_error"
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise _timeout_error(self.timeout) from exc
        except (OSError, http.client.HTTPException) as exc:
            raise CurlSMSError(
                f"Connection to {self.base_url} failed: {exc}", code="network_error"
            ) from exc


Client = CurlSMS
"""Alias of :class:`CurlSMS`."""


def _sms_path(id: str) -> str:
    if not id:
        raise ValueError("id must not be empty.")
    return "/api/sms/" + urllib.parse.quote(id, safe="")


def _format_send_at(value: datetime | str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "send_at must be timezone-aware, for example "
                "datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)."
            )
        return value.isoformat()
    if isinstance(value, str):
        return value
    raise TypeError("send_at must be a datetime or an RFC 3339 string.")


def _backoff(attempt: int) -> float:
    return float(_INITIAL_BACKOFF * (2**attempt))


def _timeout_error(timeout: float) -> CurlSMSError:
    return CurlSMSError(f"The request timed out after {timeout:g} s.", code="timeout")


def _header_map(headers: _HeaderMap | None) -> dict[str, str]:
    if headers is None:
        return {}
    return {name.lower(): str(value) for name, value in headers.items()}


def _decode_json(status: int, raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise CurlSMSError(
            "The API returned a response that is not valid JSON.",
            code="invalid_response",
            status=status,
        ) from exc


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        seconds = (when - datetime.now(timezone.utc)).total_seconds()
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)


def _error_from_response(status: int, headers: Mapping[str, str], raw: bytes) -> CurlSMSError:
    retry_after = _parse_retry_after(headers.get("retry-after"))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError:
        payload = None
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        if isinstance(code, str) and isinstance(message, str):
            index = error.get("index")
            error_id = error.get("error_id")
            return CurlSMSError(
                message,
                code=code,
                status=status,
                index=index if isinstance(index, int) and not isinstance(index, bool) else None,
                error_id=error_id if isinstance(error_id, str) else None,
                retry_after=retry_after,
            )
    return CurlSMSError(
        f"Unexpected HTTP {status} response from the API.",
        code="invalid_response",
        status=status,
        retry_after=retry_after,
    )
