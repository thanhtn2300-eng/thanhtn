"""Chuyển nội dung sang Markdown.

Markdown giữ được cấu trúc (heading, danh sách, bảng) mà text phẳng làm mất.
Với văn bản pháp luật, bảng biểu (biểu phí, phụ lục, danh mục) là nơi hay bị
nát nhất khi rút text thô — mất bảng là mất luôn khả năng trả lời đúng.

Hai đường vào:
  - `html_to_markdown()` cho nội dung lấy từ web (markdownify)
  - `file_to_markdown()` cho tệp đính kèm PDF/DOCX (markitdown)
Cả hai đều có fallback nên thiếu thư viện vẫn chạy được, chỉ kém chất lượng hơn.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_WARNED: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _WARNED:
        _WARNED.add(key)
        log.warning(message)


def clean_markdown(md: str) -> str:
    """Gom khoảng trắng thừa, giữ tối đa 1 dòng trống giữa các khối."""
    md = re.sub(r"[ \t\xa0]+", " ", md or "")
    md = re.sub(r" *\n *", "\n", md)
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def html_to_markdown(html: str) -> str:
    """HTML -> Markdown, giữ heading/list/bảng."""
    try:
        from markdownify import markdownify

        return clean_markdown(
            markdownify(html, heading_style="ATX", strip=["script", "style", "a"])
        )
    except ImportError:
        _warn_once(
            "markdownify",
            "Chưa cài markdownify — tạm rút text phẳng, sẽ mất bảng biểu. "
            "Cài bằng: pip install markdownify",
        )
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return clean_markdown(soup.get_text("\n"))


def file_to_markdown(path: str | Path) -> str:
    """PDF/DOCX -> Markdown bằng markitdown, lùi về rút text thô nếu thiếu."""
    path = Path(path)
    try:
        from markitdown import MarkItDown

        result = MarkItDown().convert(str(path))
        return clean_markdown(getattr(result, "text_content", "") or "")
    except ImportError:
        _warn_once(
            "markitdown",
            "Chưa cài markitdown — tạm rút text thô từ tệp đính kèm. "
            "Cài bằng: pip install markitdown",
        )
    except Exception as exc:  # noqa: BLE001 - một tệp hỏng không được làm chết job
        log.error("markitdown không đọc được %s: %s", path.name, exc)

    from .download import extract_text

    return clean_markdown(extract_text(path))
