"""HTTP client cho vbpl.vn: session dùng lại, rate limit, retry có backoff."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

BASE = "https://vbpl.vn"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass
class ClientConfig:
    delay: float = 1.5  # giây giữa 2 request, đừng hạ quá thấp
    jitter: float = 0.5
    timeout: int = 40
    max_retries: int = 4
    proxies: dict | None = None


class VbplClient:
    def __init__(self, config: ClientConfig | None = None):
        self.cfg = config or ClientConfig()
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if self.cfg.proxies:
            self.session.proxies.update(self.cfg.proxies)
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self.cfg.delay + random.uniform(0, self.cfg.jitter)
        elapsed = time.monotonic() - self._last_request
        if elapsed < wait:
            time.sleep(wait - elapsed)
        self._last_request = time.monotonic()

    def get(self, url: str, **kwargs) -> requests.Response:
        """GET có retry. Ném exception nếu hết số lần thử."""
        if url.startswith("/"):
            url = BASE + url
        last_exc: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            self._throttle()
            try:
                resp = self.session.get(url, timeout=self.cfg.timeout, **kwargs)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                resp.raise_for_status()
                # vbpl.vn trả về UTF-8 nhưng đôi khi thiếu charset trong header
                if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = "utf-8"
                return resp
            except Exception as exc:  # noqa: BLE001 - retry mọi lỗi mạng
                last_exc = exc
                backoff = 2**attempt
                log.warning(
                    "GET %s thất bại (lần %d/%d): %s — chờ %ds",
                    url,
                    attempt + 1,
                    self.cfg.max_retries,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
        raise RuntimeError(f"Không tải được {url}") from last_exc
