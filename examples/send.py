"""Send one SMS and print its status.

Usage:
    export CURLSMS_API_KEY=cs_test_example
    python examples/send.py +4915123456789 "Hello from Python"
"""

import sys

from curl_sms import CurlSMS, CurlSMSError


def main() -> int:
    receiver = sys.argv[1] if len(sys.argv) > 1 else "+4915123456789"
    body = sys.argv[2] if len(sys.argv) > 2 else "Hello from Python"

    client = CurlSMS()
    try:
        message = client.send(receiver, body)
    except CurlSMSError as err:
        print(f"Sending failed: {err}", file=sys.stderr)
        return 1

    parts = message["segments"]
    print(f"{message['id']}: {message['status']} ({parts} part(s), {message['price']} EUR)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
