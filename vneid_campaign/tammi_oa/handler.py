"""Xử lý sự kiện webhook Zalo OA — tách khỏi HTTP server để test không cần mạng."""

from __future__ import annotations

import logging
import re
import unicodedata

from . import messages
from .config import Config
from .store import Store
from .zalo import ZaloClient

log = logging.getLogger(__name__)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def wants_guide(text: str) -> bool:
    padded = f" {normalize(text)} "
    return any(f" {kw} " in padded for kw in messages.TU_KHOA_HUONG_DAN)


class Handler:
    def __init__(self, cfg: Config, store: Store, zalo: ZaloClient):
        self.cfg, self.store, self.zalo = cfg, store, zalo

    def process(self, event: dict) -> None:
        name = event.get("event_name", "")
        if name == "follow":
            user_id = (event.get("follower") or {}).get("id")
            if user_id:
                self.store.touch_user(user_id)
                self.zalo.send_text(user_id, messages.CHAO_MUNG)
        elif name == "user_send_image":
            self._on_image(event)
        elif name == "user_send_text":
            self._on_text(event)
        else:
            log.debug("Bỏ qua sự kiện %s", name)

    def _on_text(self, event: dict) -> None:
        user_id = (event.get("sender") or {}).get("id")
        text = (event.get("message") or {}).get("text", "")
        if not user_id:
            return
        self.store.touch_user(user_id, text)
        if wants_guide(text):
            self.zalo.send_text(user_id, messages.HUONG_DAN)
        # Tin khác (vd. "Nguyễn Văn A – Tổ 5") chỉ lưu lại để đối chiếu khi duyệt;
        # không tự trả lời để cán bộ còn trò chuyện trực tiếp trên OA.

    def _on_image(self, event: dict) -> None:
        user_id = (event.get("sender") or {}).get("id")
        msg = event.get("message") or {}
        msg_id = str(msg.get("msg_id") or event.get("timestamp") or "")
        if not user_id or not msg_id:
            log.warning("Sự kiện ảnh thiếu sender/msg_id: %s", event)
            return
        caption = msg.get("text") or ""
        self.store.touch_user(user_id, caption or None)
        is_first = self.store.count_for_user(user_id) == 0

        added = 0
        images = [a for a in msg.get("attachments") or [] if a.get("type") == "image"]
        for i, att in enumerate(images):
            url = (att.get("payload") or {}).get("url", "")
            key = msg_id if len(images) == 1 else f"{msg_id}#{i}"
            local = self._save(url, user_id, key)
            if self.store.add_submission(key, user_id, url, local, caption):
                added += 1

        if added == 0:
            return  # webhook lặp hoặc không có ảnh — đừng cảm ơn hai lần
        self.zalo.send_text(
            user_id, messages.DA_NHAN_ANH_LAN_DAU if is_first else messages.DA_NHAN_ANH_LAN_SAU
        )

    def _save(self, url: str, user_id: str, key: str) -> str | None:
        if not url:
            return None
        dest = self.cfg.image_dir / _safe(user_id) / f"{_safe(key)}.jpg"
        if dest.exists():
            return str(dest)
        try:
            return str(self.zalo.download_image(url, dest))
        except Exception as exc:  # link hỏng không được làm mất bản ghi — vẫn còn image_url
            log.error("Không tải được ảnh %s: %s", url, exc)
            return None
