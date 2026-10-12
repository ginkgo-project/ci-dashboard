"""A stand-in for status.fetch.Fetcher that serves canned responses."""

import copy
import urllib.parse

from status.fetch import FetchError

IGNORED_PARAMS = ("per_page", "page")


def key(url: str, params: dict | None = None) -> str:
    kept = sorted((k, v) for k, v in (params or {}).items() if k not in IGNORED_PARAMS)
    return f"{url}?{urllib.parse.urlencode(kept)}" if kept else url


class FakeFetcher:
    """Looks up key(url, params) first, then the bare URL."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.requested: list[str] = []

    def _get(self, url, params):
        if int((params or {}).get("page", 1)) > 1:
            raise AssertionError(f"unexpected second page of {url}")
        for candidate in (key(url, params), url):
            if candidate in self.responses:
                self.requested.append(candidate)
                return copy.deepcopy(self.responses[candidate])
        raise FetchError(f"no canned response for {key(url, params)}")

    def json(self, url, params=None):
        return self._get(url, params)

    def text(self, url, params=None):
        return self._get(url, params)
