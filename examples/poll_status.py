"""Poll for status changes of all SMS.

Usage:
    export CURLSMS_API_KEY=cs_test_example
    python examples/poll_status.py
"""

import contextlib
import time

from curl_sms import CurlSMS


def main() -> None:
    client = CurlSMS()
    page = client.list(limit=100)
    cursor = page["next_cursor"]
    print(f"{len(page['data'])} SMS so far. Waiting for changes (Ctrl+C to stop).")

    while True:
        time.sleep(10)
        page = client.list(since=cursor)
        for message in page["data"]:
            print(f"{message['id']} {message['receiver']}: {message['status']}")
        cursor = page["next_cursor"]


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
