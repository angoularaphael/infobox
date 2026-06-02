"""Session HTTP avec empreinte navigateur (curl_cffi) ou repli cloudscraper."""
from __future__ import annotations

from typing import Any

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class HttpSession:
    """Interface minimale compatible requests pour BoxRecClient."""

    def get(self, url: str, *, timeout: int = 45, **kwargs: Any):
        raise NotImplementedError

    def post(self, url: str, *, data: dict[str, str] | None = None, headers: dict[str, str] | None = None, timeout: int = 45, allow_redirects: bool = True, **kwargs: Any):
        raise NotImplementedError


def create_http_session() -> HttpSession:
    try:
        from curl_cffi.requests import Session

        class CurlAdapter(HttpSession):
            def __init__(self) -> None:
                self._session = Session(impersonate="chrome124")
                self.headers: dict[str, str] = {
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-GB,en;q=0.9,fr;q=0.8",
                }

            def get(self, url: str, *, timeout: int = 45, **kwargs: Any):
                return self._session.get(url, headers=self.headers, timeout=timeout, **kwargs)

            def post(self, url: str, *, data=None, headers=None, timeout: int = 45, allow_redirects: bool = True, **kwargs: Any):
                merged = {**self.headers, **(headers or {})}
                return self._session.post(
                    url,
                    data=data,
                    headers=merged,
                    timeout=timeout,
                    allow_redirects=allow_redirects,
                    **kwargs,
                )

        return CurlAdapter()
    except ImportError:
        pass

    import cloudscraper

    class CloudAdapter(HttpSession):
        def __init__(self) -> None:
            self._session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            self.headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9,fr;q=0.8",
            }
            self._session.headers.update(self.headers)

        def get(self, url: str, *, timeout: int = 45, **kwargs: Any):
            return self._session.get(url, timeout=timeout, **kwargs)

        def post(self, url: str, *, data=None, headers=None, timeout: int = 45, allow_redirects: bool = True, **kwargs: Any):
            return self._session.post(
                url,
                data=data,
                headers=headers,
                timeout=timeout,
                allow_redirects=allow_redirects,
                **kwargs,
            )

    return CloudAdapter()


def session_backend_name() -> str:
    try:
        from curl_cffi.requests import Session  # noqa: F401

        return "curl_cffi"
    except ImportError:
        return "cloudscraper"
