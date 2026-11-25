"""Receive and verify curl-sms webhooks with Flask.

Usage:
    pip install flask
    export CURLSMS_WEBHOOK_SECRET=whsec_...
    flask --app examples/webhook_flask.py run --port 8000
"""

import os

from flask import Flask, abort, request

from curl_sms import CurlSMSError, parse_webhook

app = Flask(__name__)
WEBHOOK_SECRET = os.environ["CURLSMS_WEBHOOK_SECRET"]
seen_events: set = set()


@app.post("/webhooks/curl-sms")
def curl_sms_webhook() -> tuple:
    try:
        event = parse_webhook(
            WEBHOOK_SECRET,
            request.headers.get("X-CurlSMS-Signature"),
            request.get_data(),
        )
    except CurlSMSError:
        abort(400)

    # Delivery is at-least-once: ignore events that were already handled.
    if event["id"] in seen_events:
        return "", 204
    seen_events.add(event["id"])

    if event["type"] == "sms.status_changed":
        data = event["data"]
        print(f"SMS {data['id']} is now {data['status']}")
    elif event["type"] == "billing.balance_low":
        print(f"Balance low: {event['data']['balance_cents'] / 100:.2f} EUR")
    else:
        print(f"Received {event['type']}")
    return "", 204
