"""Chia văn bản pháp luật thành chunk cho RAG.

Cắt theo cấu trúc pháp lý (Chương / Mục / Điều) thay vì cắt theo số ký tự cố định:
một "Điều" là đơn vị trích dẫn tự nhiên, giữ nguyên nó thì câu trả lời của RAG
mới trích dẫn được đúng "Điều X" và người dùng kiểm chứng được.
"""

from __future__ import annotations

import re

# Cho phép tiền tố Markdown (#, **, >) vì nội dung nay ở dạng Markdown:
# "### Điều 1." và "**Điều 1.**" phải nhận ra như "Điều 1.".
_MD = r"^[ \t]*(?:#{1,6}[ \t]*)?(?:[*_]{1,2})?[ \t]*"
DIEU_RE = re.compile(_MD + r"(Điều\s+\d+[a-zA-Z]?\s*[.．:-]?)(.*)$", re.M)
CHUONG_RE = re.compile(_MD + r"(Chương\s+[IVXLCDM\d]+)\b(.*)$", re.M | re.I)
MUC_RE = re.compile(_MD + r"(Mục\s+\d+)\b(.*)$", re.M | re.I)


def _headings(text: str, regex: re.Pattern) -> list[tuple[int, str]]:
    return [(m.start(), (m.group(1) + " " + m.group(2)).strip()) for m in regex.finditer(text)]


def _context_at(pos: int, headings: list[tuple[int, str]]) -> str:
    current = ""
    for start, title in headings:
        if start <= pos:
            current = title
        else:
            break
    return current


def split_by_dieu(text: str) -> list[dict]:
    """Cắt toàn văn thành các Điều, kèm ngữ cảnh Chương/Mục."""
    chuongs = _headings(text, CHUONG_RE)
    mucs = _headings(text, MUC_RE)
    matches = list(DIEU_RE.finditer(text))

    if not matches:
        return [{"dieu": "", "chuong": "", "muc": "", "text": text.strip()}] if text.strip() else []

    chunks = []
    # Phần mở đầu (căn cứ pháp lý, cơ quan ban hành) trước Điều 1 vẫn hữu ích khi truy hồi.
    preamble = text[: matches[0].start()].strip()
    if preamble:
        chunks.append({"dieu": "", "chuong": "", "muc": "", "text": preamble})

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.start() : end].strip()
        if not body:
            continue
        chunks.append(
            {
                "dieu": m.group(1).strip(" .:-"),
                "chuong": _context_at(m.start(), chuongs),
                "muc": _context_at(m.start(), mucs),
                "text": body,
            }
        )
    return chunks


def split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """Cắt tiếp một Điều quá dài, ưu tiên ranh giới đoạn rồi tới câu."""
    if len(text) <= max_chars:
        return [text]
    parts, buf = [], ""
    for para in re.split(r"\n\s*\n|(?<=\.)\s+(?=[A-ZĐ0-9])", text):
        if len(buf) + len(para) + 1 > max_chars and buf:
            parts.append(buf.strip())
            buf = buf[-overlap:] if overlap else ""
        buf += para + " "
    if buf.strip():
        parts.append(buf.strip())
    return parts


def chunk_document(doc: dict, max_chars: int = 1800, overlap: int = 150) -> list[dict]:
    """Sinh chunk kèm metadata cho một văn bản (dict lấy từ Store)."""
    meta = {
        "item_id": doc["item_id"],
        "tieu_de": doc.get("tieu_de", ""),
        "so_ky_hieu": doc.get("so_ky_hieu", ""),
        "loai_van_ban": doc.get("loai_van_ban", ""),
        "co_quan_ban_hanh": doc.get("co_quan_ban_hanh", ""),
        "ngay_ban_hanh": doc.get("ngay_ban_hanh", ""),
        "ngay_hieu_luc": doc.get("ngay_hieu_luc", ""),
        "tinh_trang": doc.get("tinh_trang", ""),
        "url": doc.get("url_toanvan", ""),
    }

    out = []
    for section in split_by_dieu(doc.get("noi_dung", "")):
        for piece in split_long(section["text"], max_chars, overlap):
            idx = len(out)
            # Nhồi tiêu đề + vị trí vào đầu chunk: embedding của một "Điều" trần
            # thường mất ngữ cảnh văn bản gốc, dễ truy hồi nhầm sang VB khác.
            header = " — ".join(
                x for x in (meta["so_ky_hieu"], meta["tieu_de"], section["chuong"], section["muc"]) if x
            )
            out.append(
                {
                    "chunk_id": f"{meta['item_id']}#{idx}",
                    **meta,
                    "chuong": section["chuong"],
                    "muc": section["muc"],
                    "dieu": section["dieu"],
                    "text": f"{header}\n\n{piece}" if header else piece,
                }
            )
    return out
