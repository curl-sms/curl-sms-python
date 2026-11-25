# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-25

### Added

- `CurlSMS` client (alias `Client`) with `send`, `estimate`, `get`, `cancel`,
  `list`, `account` and `health`.
- Sending to one receiver or up to 100 receivers, scheduling with `send_at`.
- Automatic idempotency keys for `send`, so retries never send twice.
- Retries with exponential backoff on network errors, 429 and 5xx, honoring
  `Retry-After` (capped at 30 seconds).
- `CurlSMSError` with `status`, `code`, `message`, `index`, `error_id` and
  `retry_after`.
- `verify_webhook` and `parse_webhook` for signed webhook requests.
- Type hints for all responses and webhook events (`py.typed`).
- API key from `CURLSMS_API_KEY` or `CURLSMS_KEY`.

[Unreleased]: https://github.com/curl-sms/curl-sms-python/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/curl-sms/curl-sms-python/releases/tag/v1.0.0
