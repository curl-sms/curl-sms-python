"""Typed shapes of the curl-sms API responses and webhook events.

All response objects are plain ``dict`` instances described by ``TypedDict``
classes, so they serialize to JSON unchanged. Money amounts are strings in
euros (for example ``"0.09"``), exactly as the API returns them.
"""

from __future__ import annotations

from typing import List, Literal, Optional, TypedDict, Union

__all__ = [
    "Account",
    "ApiErrorBody",
    "BalanceLow",
    "BalanceLowEvent",
    "Encoding",
    "ErrorCode",
    "Estimate",
    "HealthResponse",
    "ListResponse",
    "Message",
    "Mode",
    "QuotaWarning",
    "QuotaWarningEvent",
    "SendManyResponse",
    "SpendLimitReached",
    "SpendLimitReachedEvent",
    "Status",
    "StatusChanged",
    "StatusChangedEvent",
    "TestEvent",
    "TestEventData",
    "WebhookEvent",
    "WebhookEventType",
]

Status = Literal[
    "scheduled",
    "queued",
    "dispatched",
    "sent",
    "delivered",
    "failed",
    "expired",
    "canceled",
]
"""Lifecycle of an SMS: ``scheduled`` -> ``queued`` -> ``dispatched`` -> ``sent``
-> ``delivered``; also ``failed``, ``expired`` and ``canceled``."""

ErrorCode = Literal[
    "unauthorized",
    "invalid_json",
    "invalid_receiver",
    "ambiguous_receiver",
    "body_empty",
    "body_invalid_utf8",
    "body_too_long",
    "too_many_receivers",
    "send_at_out_of_range",
    "invalid_idempotency_key",
    "idempotency_key_mismatch",
    "idempotency_in_progress",
    "invalid_cursor",
    "payload_too_large",
    "not_found",
    "not_cancelable",
    "rate_limited",
    "daily_limit",
    "destination_blocked",
    "free_zone_only",
    "stop_listed",
    "suspended",
    "verification_required",
    "insufficient_balance",
    "spend_limit",
    "internal",
]
"""Error codes the API returns in ``{"error": {"code": ...}}``."""

Mode = Literal["live", "test"]
Encoding = Literal["gsm7", "ucs2"]
WebhookEventType = Literal[
    "sms.status_changed",
    "billing.quota_warning",
    "billing.spend_limit_reached",
    "billing.balance_low",
    "webhook.test",
]


class Message(TypedDict):
    """One SMS."""

    id: str
    mode: Mode
    receiver: str
    status: Status
    segments: int
    encoding: Encoding
    price: str
    error_code: Optional[str]
    created_at: str
    send_at: Optional[str]
    sent_at: Optional[str]
    delivered_at: Optional[str]
    refunded: bool


class SendManyResponse(TypedDict):
    """Response of a send with ``receivers``."""

    ids: List[str]
    messages: List[Message]


class _EstimateRequired(TypedDict):
    encoding: Encoding
    segments: int
    price: str
    allowed: bool


class Estimate(_EstimateRequired, total=False):
    """Encoding, parts and price of a text; ``code`` is set if not allowed."""

    code: str


class ListResponse(TypedDict):
    """A page of SMS. Pass ``next_cursor`` as ``since`` to get later changes."""

    data: List[Message]
    next_cursor: str


class Account(TypedDict):
    """Plan, quota, balance and limits of the account."""

    plan: str
    mode: Mode
    included_total: int
    included_left: int
    balance: str
    spend_limit: str
    spent: str
    daily_limit: int
    daily_left: int


class HealthResponse(TypedDict):
    """Response of the health check."""

    ok: bool
    version: str


class _ApiErrorBodyRequired(TypedDict):
    code: ErrorCode
    message: str


class ApiErrorBody(_ApiErrorBodyRequired, total=False):
    """The ``error`` object of an API error response."""

    index: int
    error_id: str


class _StatusChangedRequired(TypedDict):
    id: str
    status: Status
    at: str


class StatusChanged(_StatusChangedRequired, total=False):
    """Data of an ``sms.status_changed`` event."""

    error_code: str


class QuotaWarning(TypedDict):
    """Data of a ``billing.quota_warning`` event."""

    pct: Literal[50, 75, 100]
    used: int
    included: int
    period_start: str


class SpendLimitReached(TypedDict):
    """Data of a ``billing.spend_limit_reached`` event."""

    spent_cents: int
    limit_cents: int
    period_start: str


class BalanceLow(TypedDict):
    """Data of a ``billing.balance_low`` event."""

    balance_cents: int
    period_start: str


class TestEventData(TypedDict, total=False):
    """Data of a ``webhook.test`` event."""

    message: str


class StatusChangedEvent(TypedDict):
    id: str
    type: Literal["sms.status_changed"]
    created: int
    data: StatusChanged


class QuotaWarningEvent(TypedDict):
    id: str
    type: Literal["billing.quota_warning"]
    created: int
    data: QuotaWarning


class SpendLimitReachedEvent(TypedDict):
    id: str
    type: Literal["billing.spend_limit_reached"]
    created: int
    data: SpendLimitReached


class BalanceLowEvent(TypedDict):
    id: str
    type: Literal["billing.balance_low"]
    created: int
    data: BalanceLow


class TestEvent(TypedDict):
    id: str
    type: Literal["webhook.test"]
    created: int
    data: TestEventData


WebhookEvent = Union[
    StatusChangedEvent,
    QuotaWarningEvent,
    SpendLimitReachedEvent,
    BalanceLowEvent,
    TestEvent,
]
"""A verified webhook event. Narrow on ``event["type"]`` to get typed ``data``."""
