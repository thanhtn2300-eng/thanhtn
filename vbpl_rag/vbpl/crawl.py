"""Điều phối crawl: duyệt trang tìm kiếm -> lấy thuộc tính + toàn văn từng văn bản."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from .client import BASE, VbplClient
from .filters import SearchFilters
from .parser import Document, parse_fulltext, parse_properties, parse_search_results, parse_total_pages
from .store import Store

log = logging.getLogger(__name__)

# dvid=13 là "Văn bản pháp luật Trung ương" trên vbpl.vn.
# Đổi nhánh khác (địa phương) bằng cách đổi prefix TW và dvid tương ứng.
SEARCH_PATH = "/TW/Pages/vbpq-timkiem.aspx"
PROPS_PATH = "/TW/Pages/vbpq-thuoctinh.aspx"
FULLTEXT_PATH = "/TW/Pages/vbpq-toanvan.aspx"


def search_url(filters: SearchFilters) -> str:
    return f"{BASE}{SEARCH_PATH}?{urlencode(filters.to_query_params())}"


def fetch_document(client: VbplClient, item_id: str, tieu_de: str = "") -> Document:
    doc = Document(item_id=item_id, tieu_de=tieu_de)
    doc.url_toanvan = f"{BASE}{FULLTEXT_PATH}?ItemID={item_id}"

    props_html = client.get(f"{BASE}{PROPS_PATH}?ItemID={item_id}").text
    parse_properties(props_html, doc)

    fulltext_html = client.get(doc.url_toanvan).text
    parse_fulltext(fulltext_html, doc)
    return doc


def crawl(
    store: Store,
    client: VbplClient,
    filters: SearchFilters,
    max_pages: int | None = None,
    resume: bool = True,
) -> dict:
    """Crawl theo bộ lọc tìm kiếm. Trả về thống kê."""
    stats = {"pages": 0, "found": 0, "saved": 0, "skipped": 0, "failed": 0}

    first_html = client.get(search_url(filters.at_page(1))).text
    total_pages = parse_total_pages(first_html)
    if max_pages:
        total_pages = min(total_pages, max_pages)
    log.info("Sẽ duyệt %d trang kết quả", total_pages)

    for page in range(1, total_pages + 1):
        html = first_html if page == 1 else client.get(search_url(filters.at_page(page))).text
        results = parse_search_results(html)
        stats["pages"] += 1
        stats["found"] += len(results)
        if not results:
            log.warning("Trang %d không có kết quả — dừng sớm", page)
            break

        for item in results:
            item_id = item["item_id"]
            if resume and store.has(item_id):
                stats["skipped"] += 1
                continue
            try:
                doc = fetch_document(client, item_id, item["tieu_de"])
                if not doc.noi_dung:
                    raise ValueError("không lấy được nội dung toàn văn")
                store.save(doc)
                stats["saved"] += 1
                log.info("[%d/%d] Đã lưu %s — %s", page, total_pages, item_id, doc.tieu_de[:70])
            except Exception as exc:  # noqa: BLE001 - một VB lỗi không được làm chết cả job
                stats["failed"] += 1
                store.save_failure(item_id, str(exc))
                log.error("Lỗi ItemID=%s: %s", item_id, exc)

    return stats
