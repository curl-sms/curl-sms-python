"""The single exception type raised by the curl-sms client."""

from __future__ import annotations

__all__ = ["CurlSMSError"]


class CurlSMSError(Exception):
    """An error returned by the curl-sms API or raised by the client.

    Attributes:
        status: HTTP status code, or ``None`` if no response was received.
        code: API error code (for example ``"invalid_receiver"``), or one of the
            client-side codes ``"network_error"``, ``"timeout"``,
            ``"invalid_response"``, ``"invalid_signature"`` and ``"invalid_json"``.
        message: Human-readable description.
        index: Position in ``receivers`` that caused the error, if any.
        error_id: Error ID for ``internal`` errors; quote it when contacting support.
        retry_after: Seconds to wait before retrying, from the ``Retry-After`` header.
    """

    status: int | None
    code: str
    message: str
    index: int | None
    error_id: str | None
    retry_after: float | None

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status: int | None = None,
        index: int | None = None,
        error_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.index = index
        self.error_id = error_id
        self.retry_after = retry_after

    def __repr__(self) -> str:
        return f"CurlSMSError(status={self.status!r}, code={self.code!r}, message={self.message!r})"
