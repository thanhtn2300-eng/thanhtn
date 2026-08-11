"""Tải tệp đính kèm (PDF/DOC) và rút text làm nội dung dự phòng.

Nhiều văn bản trên vbpl.vn có trang toàn văn rỗng hoặc chỉ là ảnh scan, nội dung
thật nằm trong tệp đính kèm. Không lấy phần này thì RAG mất hẳn những văn bản đó.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import unquote, urljoin

from .client import BASE, VbplClient

log = logging.getLogger(__name__)


def _safe_name(url: str, item_id: str) -> str:
    name = unquote(url.split("?")[0].rstrip("/").split("/")[-1]) or "file"
    name = re.sub(r"[^\w.\-]+", "_", name)[:120]
    return f"{item_id}__{name}"


def download_attachments(client: VbplClient, doc: dict, out_dir: str | Path) -> list[str]:
    """Tải các tệp đính kèm của một văn bản. Trả về danh sách đường dẫn đã lưu."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for href in doc.get("tep_dinh_kem") or []:
        url = urljoin(BASE, href)
        dest = out_dir / _safe_name(url, doc["item_id"])
        if dest.exists() and dest.stat().st_size > 0:
            saved.append(str(dest))
            continue
        try:
            resp = client.get(url)
            dest.write_bytes(resp.content)
            saved.append(str(dest))
            log.info("Đã tải %s (%d KB)", dest.name, len(resp.content) // 1024)
        except Exception as exc:  # noqa: BLE001 - một tệp lỗi không làm chết job
            log.error("Không tải được %s: %s", url, exc)
    return saved


def extract_text(path: str | Path) -> str:
    """Rút text từ PDF/DOCX. Trả về chuỗi rỗng nếu thiếu thư viện hoặc file là ảnh scan."""
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if suffix == ".docx":
            import docx

            return "\n".join(p.text for p in docx.Document(str(path)).paragraphs).strip()
    except ImportError as exc:
        log.warning("Thiếu thư viện để đọc %s: %s (pip install pypdf python-docx)", suffix, exc)
    except Exception as exc:  # noqa: BLE001
        log.error("Không đọc được %s: %s", path.name, exc)
    return ""
