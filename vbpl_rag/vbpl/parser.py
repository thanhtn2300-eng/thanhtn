"""Parse HTML của vbpl.vn.

LƯU Ý: vbpl.vn không có API JSON, cấu trúc HTML do site tự render và có thể đổi.
Mọi hàm ở đây đều parse "phòng thủ": thử selector chính, rồi fallback heuristic,
và không bao giờ ném exception khi chỉ thiếu một trường.
Chạy `python -m vbpl.cli probe --item-id <id>` để kiểm chứng selector trên HTML thật.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict

from bs4 import BeautifulSoup

ITEM_ID_RE = re.compile(r"ItemID=(\d+)", re.I)

# Nhãn thuộc tính -> tên trường chuẩn hoá
FIELD_MAP = {
    "so ky hieu": "so_ky_hieu",
    "ngay ban hanh": "ngay_ban_hanh",
    "loai van ban": "loai_van_ban",
    "co quan ban hanh": "co_quan_ban_hanh",
    "nguoi ky": "nguoi_ky",
    "ngay co hieu luc": "ngay_hieu_luc",
    "ngay het hieu luc": "ngay_het_hieu_luc",
    "ngay dang cong bao": "ngay_cong_bao",
    "tinh trang hieu luc": "tinh_trang",
    "trich yeu": "trich_yeu",
    "linh vuc": "linh_vuc",
}


def _norm(text: str) -> str:
    """Bỏ dấu + lowercase để so khớp nhãn tiếng Việt bất kể cách viết hoa/dấu."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def _clean(text: str) -> str:
    return re.sub(r"[ \t\xa0]+", " ", (text or "")).strip()


@dataclass
class Document:
    item_id: str
    tieu_de: str = ""
    so_ky_hieu: str = ""
    ngay_ban_hanh: str = ""
    loai_van_ban: str = ""
    co_quan_ban_hanh: str = ""
    nguoi_ky: str = ""
    ngay_hieu_luc: str = ""
    ngay_het_hieu_luc: str = ""
    ngay_cong_bao: str = ""
    tinh_trang: str = ""
    trich_yeu: str = ""
    linh_vuc: str = ""
    url_toanvan: str = ""
    noi_dung: str = ""
    tep_dinh_kem: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("noi_dung_is_html", None)  # cờ tạm trong lúc parse, không lưu vào DB
        return data

    # Đánh dấu nội dung còn ở dạng HTML để tầng trên quyết định có chuyển Markdown không.
    noi_dung_is_html: bool = False


def parse_search_results(html: str) -> list[dict]:
    """Lấy danh sách (item_id, tiêu đề, url) từ trang tìm kiếm."""
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, dict] = {}
    for a in soup.select("a[href*='ItemID=']"):
        m = ITEM_ID_RE.search(a.get("href", ""))
        if not m:
            continue
        item_id = m.group(1)
        title = _clean(a.get_text())
        # Trang có nhiều link tới cùng ItemID (tiêu đề, "xem toàn văn", icon...).
        # Giữ link có text dài nhất — gần như luôn là tiêu đề văn bản.
        prev = seen.get(item_id)
        if prev is None or len(title) > len(prev["tieu_de"]):
            seen[item_id] = {
                "item_id": item_id,
                "tieu_de": title,
                "url": a.get("href", ""),
            }
    return [v for v in seen.values() if v["tieu_de"]]


def parse_total_pages(html: str) -> int:
    """Đoán tổng số trang từ khối phân trang. Trả về 1 nếu không xác định được."""
    soup = BeautifulSoup(html, "html.parser")
    pages = {1}
    for a in soup.select("a[href*='Page=']"):
        m = re.search(r"[?&]Page=(\d+)", a.get("href", ""))
        if m:
            pages.add(int(m.group(1)))
    for a in soup.select("a[onclick*='Page']"):
        for m in re.finditer(r"\b(\d{1,5})\b", a.get("onclick", "")):
            pages.add(int(m.group(1)))
    return max(pages)


def parse_properties(html: str, doc: Document) -> Document:
    """Đọc trang vbpq-thuoctinh.aspx: bảng/danh sách nhãn -> giá trị."""
    soup = BeautifulSoup(html, "html.parser")

    if not doc.tieu_de:
        for sel in ("h3", "h2", ".header h3", ".title"):
            node = soup.select_one(sel)
            if node and _clean(node.get_text()):
                doc.tieu_de = _clean(node.get_text())
                break

    pairs: list[tuple[str, str]] = []
    for tr in soup.select("tr"):
        cells = tr.find_all(["td", "th"], recursive=False) or tr.find_all(["td", "th"])
        if len(cells) >= 2:
            pairs.append((cells[0].get_text(), cells[1].get_text()))
    # Bố cục dạng <li><span>Nhãn</span><p>Giá trị</p></li>
    for li in soup.select("li"):
        label = li.find(["span", "strong", "b", "label"])
        if label and label.next_sibling:
            pairs.append((label.get_text(), li.get_text().replace(label.get_text(), "", 1)))

    for raw_label, raw_value in pairs:
        key = FIELD_MAP.get(_norm(raw_label).rstrip(" :"))
        value = _clean(raw_value).lstrip(": ")
        if key and value and not getattr(doc, key):
            setattr(doc, key, value)
    return doc


# Tên trường hay gặp trong response JSON của trang chi tiết.
JSON_FIELD_KEYS = {
    "tieu_de": ("title", "Title", "tieuDe", "TieuDe", "name"),
    "so_ky_hieu": ("soKyHieu", "SoKyHieu", "code", "symbol", "documentNumber"),
    "ngay_ban_hanh": ("ngayBanHanh", "NgayBanHanh", "issuedDate", "promulgationDate"),
    "loai_van_ban": ("loaiVanBan", "LoaiVanBan", "docType", "documentType"),
    "co_quan_ban_hanh": ("coQuanBanHanh", "CoQuanBanHanh", "agency", "organ"),
    "nguoi_ky": ("nguoiKy", "NguoiKy", "signer"),
    "ngay_hieu_luc": ("ngayHieuLuc", "NgayHieuLuc", "effectiveDate"),
    "ngay_het_hieu_luc": ("ngayHetHieuLuc", "expiredDate", "expiryDate"),
    "tinh_trang": ("tinhTrang", "TinhTrang", "effStatus", "status", "effectStatus"),
    "trich_yeu": ("trichYeu", "TrichYeu", "summary", "abstract"),
    "linh_vuc": ("linhVuc", "LinhVuc", "fieldType", "field"),
}
JSON_CONTENT_KEYS = ("content", "Content", "noiDung", "NoiDung", "fullText", "body", "html")
JSON_FILE_KEYS = ("files", "attachments", "tepDinhKem", "fileUrl", "attachmentUrl")


def parse_detail_json(payload: dict, doc: Document) -> Document:
    """Đọc response JSON của trang chi tiết.

    Tên trường chưa xác minh được với API thật nên thử lần lượt các biến thể
    thường gặp; trường nào không khớp thì để trống chứ không ném lỗi.
    """
    # Nội dung thật có thể nằm trong một tầng bọc: {"data": {...}} / {"result": {...}}
    for wrapper in ("data", "Data", "result", "Result", "item", "document"):
        inner = payload.get(wrapper)
        if isinstance(inner, dict):
            payload = {**payload, **inner}
            break

    for field_name, candidates in JSON_FIELD_KEYS.items():
        if getattr(doc, field_name):
            continue
        for key in candidates:
            value = payload.get(key)
            if isinstance(value, dict):  # {"id": 1, "name": "Luật"}
                value = value.get("name") or value.get("Name") or value.get("text")
            if value not in (None, "", []):
                setattr(doc, field_name, _clean(str(value)))
                break

    for key in JSON_CONTENT_KEYS:
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            # Nội dung thường là HTML nhúng trong JSON, không phải text thuần.
            doc.noi_dung = raw if "<" not in raw else raw
            doc.noi_dung_is_html = "<" in raw
            break

    files: list[str] = []
    for key in JSON_FILE_KEYS:
        value = payload.get(key)
        if isinstance(value, str):
            files.append(value)
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    files.append(entry)
                elif isinstance(entry, dict):
                    url = entry.get("url") or entry.get("Url") or entry.get("path")
                    if url:
                        files.append(str(url))
    doc.tep_dinh_kem = sorted(set(doc.tep_dinh_kem) | set(files))
    return doc


def parse_fulltext(html: str, doc: Document, keep_html: bool = False) -> Document:
    """Đọc trang vbpq-toanvan.aspx: lấy nội dung + link tệp đính kèm."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    container = None
    for sel in (
        ".toanvancontent",
        "#toanvancontent",
        ".fulltext",
        ".content1",
        ".vbProperties",
        "#divContent",
    ):
        container = soup.select_one(sel)
        if container:
            break
    if container is None:
        # Fallback: khối <div> có nhiều text nhất — toàn văn luôn là phần dài nhất trang.
        divs = soup.find_all("div")
        container = max(divs, key=lambda d: len(d.get_text()), default=None)

    if container is not None:
        if keep_html:
            # Giữ HTML để tầng trên chuyển sang Markdown — rút text ở đây sẽ mất bảng biểu.
            doc.noi_dung = str(container)
            doc.noi_dung_is_html = True
        else:
            lines = [_clean(l) for l in container.get_text("\n").split("\n")]
            doc.noi_dung = re.sub(r"\n{3,}", "\n\n", "\n".join(l for l in lines if l))

    for a in soup.select("a[href]"):
        href = a["href"]
        if re.search(r"\.(pdf|docx?|rtf|zip)(\?|$)", href, re.I):
            doc.tep_dinh_kem.append(href)
    doc.tep_dinh_kem = sorted(set(doc.tep_dinh_kem))
    return doc
