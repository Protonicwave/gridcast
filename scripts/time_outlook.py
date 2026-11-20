"""Times one path of a deployed API against a response-time budget.

Usage: uv run python scripts/time_outlook.py https://<api host>
[--path /accuracy/national] [--budget-ms 1000]

The path defaults to London's outlook and the budget to 500 ms. Prints the first
request's time, which includes a cold start if the app had scaled to zero, then the
median of the warm requests that follow. Each request opens its own connection, as a
browser's first call does. Exits 0 when the median is within budget, 1 when it is over,
and 2 when a request fails or the URL or path is invalid.
"""

import argparse
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from urllib.parse import urlsplit

DEFAULT_BUDGET_MEDIAN_MS = 500
WARM_REQUESTS = 20
# Long enough for a replica to start from zero, which the first request may wait for.
REQUEST_TIMEOUT_SECONDS = 60
DEFAULT_PATH = "/regions/13/outlook"
EXIT_OVER_BUDGET = 1
EXIT_FAILED = 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("api_url", help="the API's origin, for example https://example.org")
    parser.add_argument("--path", default=DEFAULT_PATH, help="the path to time, with any query")
    parser.add_argument(
        "--budget-ms", type=int, default=DEFAULT_BUDGET_MEDIAN_MS, help="the median's limit"
    )
    arguments = parser.parse_args(argv)
    api_url: str = arguments.api_url
    parts = urlsplit(api_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        print(
            f"time_outlook: expected an http(s) URL with a host, got {api_url!r}", file=sys.stderr
        )
        return EXIT_FAILED
    if not arguments.path.startswith("/"):
        print(
            f"time_outlook: expected a path starting with /, got {arguments.path!r}",
            file=sys.stderr,
        )
        return EXIT_FAILED
    url = api_url.rstrip("/") + arguments.path
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
        f" budget {arguments.budget_ms} ms"
    )
    return 0 if median_ms < arguments.budget_ms else EXIT_OVER_BUDGET


def _time_request_ms(url: str) -> float:
    started = time.perf_counter()
    # S310 warns of file: and custom schemes; main admits only http and https.
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
        response.read()
    return (time.perf_counter() - started) * 1000


if __name__ == "__main__":
    sys.exit(main())
