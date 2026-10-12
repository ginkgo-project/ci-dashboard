import io
import urllib.error

import pytest

from status.fetch import FetchError, Fetcher, paged


def test_retries_server_errors_with_growing_waits():
    calls, sleeps = [], []

    def opener(request, timeout):
        calls.append(request.full_url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(request.full_url, 502, "bad gateway", None, None)
        return io.BytesIO(b'{"ok": true}')

    fetcher = Fetcher(opener=opener, sleep=sleeps.append)
    assert fetcher.json("https://gitlab.com/api/v4/x", {"a": 1}) == {"ok": True}
    assert calls == ["https://gitlab.com/api/v4/x?a=1"] * 3
    assert sleeps == [2.0, 4.0]


def test_does_not_retry_forbidden():
    calls = []

    def opener(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 403, "rate limit exceeded", None, None)

    fetcher = Fetcher(opener=opener, sleep=lambda seconds: pytest.fail("no retry expected"))
    with pytest.raises(FetchError, match="403"):
        fetcher.json("https://api.github.com/x")
    assert calls == [1]


def test_gives_up_after_three_retries():
    calls = []

    def opener(request, timeout):
        calls.append(1)
        raise urllib.error.URLError("connection refused")

    with pytest.raises(FetchError, match="connection refused"):
        Fetcher(opener=opener, sleep=lambda seconds: None).text("https://gitlab.com/x")
    assert len(calls) == 4


def test_github_token_is_only_sent_to_github():
    seen = {}

    def opener(request, timeout):
        seen[request.full_url] = request.get_header("Authorization")
        return io.BytesIO(b"[]")

    fetcher = Fetcher(github_token="secret", opener=opener, sleep=None)
    fetcher.json("https://api.github.com/a")
    fetcher.json("https://gitlab.com/api/v4/b")
    assert seen == {"https://api.github.com/a": "Bearer secret",
                    "https://gitlab.com/api/v4/b": None}


class Pages:
    def __init__(self, sizes):
        self.sizes = sizes
        self.pages = []

    def json(self, url, params=None):
        self.pages.append(params["page"])
        return {"items": list(range(self.sizes[params["page"] - 1]))}


def test_paged_reads_until_a_short_page():
    pages = Pages([100, 3])
    assert len(paged(pages, "u", {"a": 1}, key="items")) == 103
    assert pages.pages == [1, 2]


def test_paged_stops_at_the_limit():
    pages = Pages([10, 10])
    assert len(paged(pages, "u", key="items", per_page=10, limit=10)) == 10
    assert pages.pages == [1]
