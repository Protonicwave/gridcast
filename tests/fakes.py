"""A stand-in for urlopen, the collector's network boundary."""

import io
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from email.message import Message


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__(body)
        self.status = status


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.invalid/", code, "Reason", Message(), None)


class FakeServer:
    """Answers each request with the next scripted outcome and records what was asked."""

    def __init__(self, *outcomes: FakeResponse | Exception) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[tuple[str, float]] = []

    @contextmanager
    def urlopen(self, request: urllib.request.Request, timeout: float) -> Iterator[FakeResponse]:
        self.requests.append((request.full_url, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome
