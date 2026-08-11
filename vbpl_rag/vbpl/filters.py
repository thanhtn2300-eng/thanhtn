"""Bộ lọc tìm kiếm vbpl.vn, tách riêng khỏi tầng gọi mạng.

Cùng một bộ lọc được render ra hai dạng:
  - `to_query_params()` cho trang HTML vbpq-timkiem.aspx (đường đi đã hoạt động)
  - `to_json_body()`    cho endpoint JSON, nếu/khi xác định được endpoint đó

Nhờ vậy đổi backend chỉ sửa một chỗ, phần crawl/parse/chunk giữ nguyên.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# effStatus: trạng thái hiệu lực. Đây là bộ lọc quan trọng nhất cho RAG pháp luật —
# trả lời theo văn bản đã hết hiệu lực là lỗi nguy hiểm nhất của hệ thống.
EFF_STATUS = {
    "con-hieu-luc": 1,
    "het-hieu-luc": 2,
    "chua-co-hieu-luc": 3,
    "khong-con-phu-hop": 4,
}

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _csv(values: list[str | int] | None) -> str:
    return ",".join(str(v) for v in values) if values else ""


@dataclass
class SearchFilters:
    keyword: str = ""
    doc_type: str | int | None = None          # loại văn bản (Luật, Nghị định, Thông tư...)
    agency_ids: list[str | int] = field(default_factory=list)      # cơ quan ban hành
    field_type_ids: list[str | int] = field(default_factory=list)  # lĩnh vực
    eff_status: str | int | None = None        # tên khoá trong EFF_STATUS hoặc id số
    from_date: str = ""                        # dd/mm/yyyy
    to_date: str = ""                          # dd/mm/yyyy
    page: int = 1
    row_count: int = 20
    dvid: int = 13                             # 13 = nhánh Trung ương

    def __post_init__(self) -> None:
        for name in ("from_date", "to_date"):
            value = getattr(self, name)
            if value and not DATE_RE.match(value):
                raise ValueError(f"{name} phải theo dạng dd/mm/yyyy, nhận được {value!r}")
        if isinstance(self.eff_status, str) and self.eff_status:
            if self.eff_status not in EFF_STATUS:
                raise ValueError(
                    f"eff_status không hợp lệ: {self.eff_status!r}. "
                    f"Chọn một trong {sorted(EFF_STATUS)} hoặc truyền id số."
                )
            self.eff_status = EFF_STATUS[self.eff_status]

    def to_query_params(self) -> dict:
        """Tham số cho trang HTML tìm kiếm."""
        params = {
            "dvid": self.dvid,
            "Page": self.page,
            "RowCount": self.row_count,
            "Keyword": self.keyword,
            "type": self.doc_type,
            "organ": _csv(self.agency_ids),
            "field": _csv(self.field_type_ids),
            "EffectStatus": self.eff_status,
            "FromDate": self.from_date,
            "ToDate": self.to_date,
        }
        return {k: v for k, v in params.items() if v not in (None, "", [])}

    def to_json_body(self) -> dict:
        """Payload cho endpoint JSON, dùng đúng tên trường đã nêu."""
        body = {
            "keyword": self.keyword,
            "docType": self.doc_type,
            "agencyIds": self.agency_ids,
            "fieldTypeIds": self.field_type_ids,
            "effStatus": self.eff_status,
            "fromDate": self.from_date,
            "toDate": self.to_date,
            "page": self.page,
            "pageSize": self.row_count,
        }
        return {k: v for k, v in body.items() if v not in (None, "", [])}

    def at_page(self, page: int) -> "SearchFilters":
        return SearchFilters(**{**self.__dict__, "page": page})
