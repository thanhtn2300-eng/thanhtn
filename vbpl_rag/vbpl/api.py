"""Backend JSON API cho tìm kiếm văn bản.

Key và base URL đọc từ biến môi trường, KHÔNG hard-code vào repo:

    export VBPL_API_BASE="https://<host>/<đường-dẫn-tìm-kiếm>"
    export VBPL_API_KEY="<key 40 ký tự>"
    export VBPL_API_AUTH="bearer"   # bearer | x-api-key | query | path

Cách truyền key khác nhau tuỳ API nên để cấu hình được thay vì đoán một kiểu:
đổi `VBPL_API_AUTH` là thử được kiểu khác mà không phải sửa code.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from .client import VbplClient
from .filters import SearchFilters

log = logging.getLogger(__name__)

AUTH_MODES = ("bearer", "x-api-key", "query", "path")

# Tên trường hay gặp trong response JSON — thử lần lượt vì chưa biết schema thật.
LIST_KEYS = ("items", "data", "Data", "results", "records", "documents", "list")
TOTAL_KEYS = ("total", "totalCount", "totalRecords", "totalItems", "count", "TotalCount")
ID_KEYS = ("itemId", "ItemID", "itemID", "id", "Id", "documentId")
TITLE_KEYS = ("title", "Title", "tieuDe", "name", "trichYeu", "subject")


@dataclass
class ApiConfig:
    base_url: str = ""
    key: str = ""
    auth: str = "bearer"
    method: str = "POST"

    @classmethod
    def from_env(cls) -> "ApiConfig":
        cfg = cls(
            base_url=os.environ.get("VBPL_API_BASE", "").rstrip("/"),
            key=os.environ.get("VBPL_API_KEY", ""),
            auth=os.environ.get("VBPL_API_AUTH", "bearer").lower(),
            method=os.environ.get("VBPL_API_METHOD", "POST").upper(),
        )
        if cfg.auth not in AUTH_MODES:
            raise ValueError(f"VBPL_API_AUTH phải thuộc {AUTH_MODES}, nhận được {cfg.auth!r}")
        return cfg

    def require(self) -> None:
        missing = [n for n, v in (("VBPL_API_BASE", self.base_url), ("VBPL_API_KEY", self.key)) if not v]
        if missing:
            raise RuntimeError(
                "Thiếu biến môi trường: " + ", ".join(missing) + ". "
                "Key 40 ký tự chỉ là thông tin xác thực — vẫn cần VBPL_API_BASE "
                "là URL endpoint tìm kiếm để biết gửi request đi đâu."
            )


class JsonSearchBackend:
    """Gọi endpoint JSON, trả về cùng định dạng như parser HTML để crawl dùng chung."""

    def __init__(self, client: VbplClient, config: ApiConfig | None = None):
        self.client = client
        self.cfg = config or ApiConfig.from_env()
        self.cfg.require()

    def _request(self, filters: SearchFilters):
        url, body = self.cfg.base_url, filters.to_json_body()
        headers, params = {"Accept": "application/json"}, {}

        if self.cfg.auth == "bearer":
            headers["Authorization"] = f"Bearer {self.cfg.key}"
        elif self.cfg.auth == "x-api-key":
            headers["X-API-Key"] = self.cfg.key
        elif self.cfg.auth == "query":
            params["apiKey"] = self.cfg.key
        elif self.cfg.auth == "path":
            url = f"{url}/{self.cfg.key}"

        if self.cfg.method == "GET":
            return self.client.get(url, params={**params, **body}, headers=headers)
        # VbplClient.get đã có throttle + retry; POST đi thẳng qua session bên dưới.
        self.client._throttle()
        resp = self.client.session.post(
            url, json=body, params=params, headers=headers, timeout=self.client.cfg.timeout
        )
        resp.raise_for_status()
        return resp

    @staticmethod
    def _pick(mapping: dict, keys: tuple[str, ...]):
        for k in keys:
            if mapping.get(k) not in (None, ""):
                return mapping[k]
        return None

    def search(self, filters: SearchFilters) -> tuple[list[dict], int | None]:
        """Trả về (danh sách kết quả, tổng số bản ghi nếu API có báo)."""
        payload = self._request(filters).json()

        items = payload if isinstance(payload, list) else None
        if items is None:
            for key in LIST_KEYS:
                value = payload.get(key)
                if isinstance(value, list):
                    items = value
                    break
                # Một số API bọc thêm một tầng: {"data": {"items": [...]}}
                if isinstance(value, dict):
                    for inner in LIST_KEYS:
                        if isinstance(value.get(inner), list):
                            items = value[inner]
                            break
                if items is not None:
                    break
        if items is None:
            raise ValueError(
                f"Không tìm thấy danh sách kết quả trong response. Khoá có sẵn: {list(payload)[:12]}"
            )

        total = self._pick(payload, TOTAL_KEYS) if isinstance(payload, dict) else None

        results = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            item_id = self._pick(raw, ID_KEYS)
            if item_id is None:
                continue
            results.append(
                {
                    "item_id": str(item_id),
                    "tieu_de": str(self._pick(raw, TITLE_KEYS) or ""),
                    "url": "",
                    "raw": raw,
                }
            )
        return results, int(total) if isinstance(total, (int, str)) and str(total).isdigit() else None
