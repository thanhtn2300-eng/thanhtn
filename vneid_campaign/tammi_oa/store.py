"""Lưu ảnh người dân gửi vào SQLite để cán bộ duyệt và thống kê."""

from __future__ import annotations

import csv
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("cho_duyet", "hop_le", "khong_hop_le")

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    msg_id       TEXT PRIMARY KEY,           -- khoá chống trùng khi Zalo gửi lại webhook
    zalo_user_id TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    image_url    TEXT,
    local_path   TEXT,
    caption      TEXT,
    status       TEXT NOT NULL DEFAULT 'cho_duyet',
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_sub_user ON submissions(zalo_user_id);
CREATE TABLE IF NOT EXISTS users (
    zalo_user_id TEXT PRIMARY KEY,
    first_seen   TEXT NOT NULL,
    last_text    TEXT                         -- tin nhắn gần nhất, thường là "Tên - khu phố"
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def touch_user(self, user_id: str, text: str | None = None) -> bool:
        """Trả về True nếu đây là lần đầu người này nhắn tới OA."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO users(zalo_user_id, first_seen) VALUES (?, ?)",
                (user_id, _now()),
            )
            if text:
                self._conn.execute(
                    "UPDATE users SET last_text = ? WHERE zalo_user_id = ?", (text[:500], user_id)
                )
            return cur.rowcount == 1

    def add_submission(
        self, msg_id: str, user_id: str, image_url: str, local_path: str | None, caption: str
    ) -> bool:
        """Trả về False nếu msg_id đã có (webhook bị gửi lặp)."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO submissions"
                "(msg_id, zalo_user_id, received_at, image_url, local_path, caption)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (msg_id, user_id, _now(), image_url, local_path, caption[:500]),
            )
            return cur.rowcount == 1

    def count_for_user(self, user_id: str) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE zalo_user_id = ?", (user_id,)
            ).fetchone()[0]

    def set_status(self, msg_id: str, status: str, note: str = "") -> bool:
        if status not in STATUSES:
            raise ValueError(f"status phải thuộc {STATUSES}")
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE submissions SET status = ?, note = ? WHERE msg_id = ?",
                (status, note, msg_id),
            )
            return cur.rowcount == 1

    def list(self, status: str | None = None) -> list[sqlite3.Row]:
        sql = (
            "SELECT s.*, u.last_text FROM submissions s"
            " LEFT JOIN users u USING(zalo_user_id)"
        )
        args: tuple = ()
        if status:
            sql += " WHERE s.status = ?"
            args = (status,)
        with self._lock:
            return self._conn.execute(sql + " ORDER BY s.received_at", args).fetchall()

    def stats(self) -> dict:
        with self._lock:
            return self._stats()

    def _stats(self) -> dict:
        q = self._conn.execute
        by_status = dict(q("SELECT status, COUNT(*) FROM submissions GROUP BY status").fetchall())
        return {
            "tong_anh": sum(by_status.values()),
            "theo_trang_thai": {s: by_status.get(s, 0) for s in STATUSES},
            # Chỉ số chiến dịch thật sự cần: số NGƯỜI đã cài, không phải số ảnh.
            "so_nguoi_hop_le": q(
                "SELECT COUNT(DISTINCT zalo_user_id) FROM submissions WHERE status = 'hop_le'"
            ).fetchone()[0],
            "so_nguoi_da_gui": q(
                "SELECT COUNT(DISTINCT zalo_user_id) FROM submissions"
            ).fetchone()[0],
        }

    def export_csv(self, out: Path) -> int:
        rows = self.list()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig để Excel đọc đúng dấu
            w = csv.writer(f)
            w.writerow(
                ["msg_id", "zalo_user_id", "thoi_gian", "trang_thai", "ghi_chu",
                 "tin_nhan_kem", "tin_nhan_gan_nhat", "anh"]
            )
            for r in rows:
                w.writerow(
                    [r["msg_id"], r["zalo_user_id"], r["received_at"], r["status"], r["note"],
                     r["caption"], r["last_text"], r["local_path"]]
                )
        return len(rows)
