"""HTTP for the status fetcher: JSON and text with retries, and pagination."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

# answers that a retry won't change
NO_RETRY = (401, 403, 404, 410)


class FetchError(RuntimeError):
    pass


class Fetcher:
    """Reads URLs; retries a failed request 3 times, waiting 2, 4 and 8 s."""

    def __init__(self, github_token: str | None = None, retries: int = 3, wait: float = 2.0,
                 opener=urllib.request.urlopen, sleep=time.sleep):
        self.github_token = github_token
        self.retries = retries
        self.wait = wait
        self.opener = opener
        self.sleep = sleep

    def _request(self, url: str, params: dict | None) -> bytes:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": "ginkgo-ci-dashboard"})
        # not sent on redirects: job logs redirect to blob storage, which rejects the token
        if self.github_token and url.startswith("https://api.github.com/"):
            request.add_unredirected_header("Authorization", f"Bearer {self.github_token}")
        error: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                self.sleep(self.wait * 2 ** (attempt - 1))
            try:
                with self.opener(request, timeout=60) as response:
                    return response.read()
            except urllib.error.HTTPError as http_error:
                error = http_error
                if http_error.code in NO_RETRY:
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as network_error:
                error = network_error
        raise FetchError(f"{url}: {error}")

    def json(self, url: str, params: dict | None = None):
        return json.loads(self._request(url, params))

    def text(self, url: str, params: dict | None = None) -> str:
        return self._request(url, params).decode("utf-8", errors="replace")


def paged(fetcher, url: str, params: dict | None = None, key: str | None = None,
          per_page: int = 100, limit: int | None = None) -> list:
    """All items of a paginated GitLab or GitHub list. key picks the list out of
    a wrapping object, e.g. GitHub's {"check_runs": [...]}."""
    items: list = []
    page = 1
    while True:
        data = fetcher.json(url, {**(params or {}), "per_page": per_page, "page": page})
        batch = data[key] if key else data
        items += batch
        if len(batch) < per_page or (limit and len(items) >= limit):
            return items[:limit] if limit else items
        page += 1
