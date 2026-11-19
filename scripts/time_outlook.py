"""Times London's outlook on a deployed API against its response-time budget.

Usage: uv run python scripts/time_outlook.py https://<api host>

Prints the first request's time, which includes a cold start if the app had scaled
to zero, then the median of the warm requests that follow. Each request opens its
own connection, as a browser's first call does. Exits 0 when the median is within
budget, 1 when it is over, and 2 when a request fails or the URL is not http(s).
"""

import argparse
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from urllib.parse import urlsplit

BUDGET_MEDIAN_MS = 500
WARM_REQUESTS = 20
# Long enough for a replica to start from zero, which the first request may wait for.
REQUEST_TIMEOUT_SECONDS = 60
LONDON_OUTLOOK_PATH = "/regions/13/outlook"
EXIT_OVER_BUDGET = 1
EXIT_FAILED = 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("api_url", help="the API's origin, for example https://example.org")
    api_url: str = parser.parse_args(argv).api_url
    parts = urlsplit(api_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        print(
            f"time_outlook: expected an http(s) URL with a host, got {api_url!r}", file=sys.stderr
        )
        return EXIT_FAILED
    url = api_url.rstrip("/") + LONDON_OUTLOOK_PATH
    try:
        first_ms = _time_request_ms(url)
        warm_ms = [_time_request_ms(url) for _ in range(WARM_REQUESTS)]
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"time_outlook: GET {url} failed: {err}", file=sys.stderr)
        return EXIT_FAILED
    median_ms = statistics.median(warm_ms)
    print(f"first request {first_ms:.0f} ms (includes a cold start if the app was at zero)")
    print(
        f"warm median {median_ms:.0f} ms over {WARM_REQUESTS} requests,"
        f" budget {BUDGET_MEDIAN_MS} ms"
    )
    return 0 if median_ms < BUDGET_MEDIAN_MS else EXIT_OVER_BUDGET


def _time_request_ms(url: str) -> float:
    started = time.perf_counter()
    # S310 warns of file: and custom schemes; main admits only http and https.
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
        response.read()
    return (time.perf_counter() - started) * 1000


if __name__ == "__main__":
    sys.exit(main())
