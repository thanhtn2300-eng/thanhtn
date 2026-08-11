"""Lưu trữ: SQLite làm nguồn chuẩn + xuất JSONL cho pipeline RAG."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .parser import Document

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    item_id            TEXT PRIMARY KEY,
    tieu_de            TEXT,
    so_ky_hieu         TEXT,
    ngay_ban_hanh      TEXT,
    loai_van_ban       TEXT,
    co_quan_ban_hanh   TEXT,
    nguoi_ky           TEXT,
    ngay_hieu_luc      TEXT,
    ngay_het_hieu_luc  TEXT,
    ngay_cong_bao      TEXT,
    tinh_trang         TEXT,
    trich_yeu          TEXT,
    linh_vuc           TEXT,
    url_toanvan        TEXT,
    noi_dung           TEXT,
    tep_dinh_kem       TEXT,
    fetched_at         TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS failures (
    item_id  TEXT PRIMARY KEY,
    error    TEXT,
    tried_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_loai ON documents(loai_van_ban);
CREATE INDEX IF NOT EXISTS idx_ngay ON documents(ngay_ban_hanh);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def has(self, item_id: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM documents WHERE item_id = ? AND noi_dung != ''", (item_id,)
        )
        return cur.fetchone() is not None

    def save(self, doc: Document) -> None:
        data = doc.to_dict()
        data["tep_dinh_kem"] = json.dumps(data["tep_dinh_kem"], ensure_ascii=False)
        cols = ", ".join(data)
        placeholders = ", ".join(f":{k}" for k in data)
        self.conn.execute(
            f"INSERT OR REPLACE INTO documents ({cols}) VALUES ({placeholders})", data
        )
        self.conn.execute("DELETE FROM failures WHERE item_id = ?", (doc.item_id,))
        self.conn.commit()

    def save_failure(self, item_id: str, error: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO failures (item_id, error) VALUES (?, ?)",
            (item_id, error[:500]),
        )
        self.conn.commit()

    def iter_documents(self):
        for row in self.conn.execute("SELECT * FROM documents WHERE noi_dung != ''"):
            doc = dict(row)
            doc["tep_dinh_kem"] = json.loads(doc["tep_dinh_kem"] or "[]")
            yield doc

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def export_jsonl(self, out_path: str | Path) -> int:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with out_path.open("w", encoding="utf-8") as f:
            for doc in self.iter_documents():
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                n += 1
        return n
