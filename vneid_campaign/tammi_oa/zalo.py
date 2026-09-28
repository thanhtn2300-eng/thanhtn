"""Gọi Zalo OA Open API: xác thực webhook, gửi tin trả lời, tải ảnh, làm mới token.

Endpoint và công thức chữ ký lấy theo tài liệu Zalo OA API v3 (developers.zalo.me).
Chưa chạy được với OA thật trong môi trường tạo repo này — xem mục "Trạng thái
kiểm thử" trong README trước khi mở chiến dịch.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)

SEND_URL = "https://openapi.zalo.me/v3.0/oa/message/cs"
TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"
MAX_IMAGE_BYTES = 15 * 1024 * 1024


def verify_signature(cfg: Config, raw_body: bytes, header: str | None) -> bool:
    """Header `X-ZEvent-Signature: mac=<sha256(app_id + body + timestamp + oa_secret_key)>`."""
    if not cfg.verify_signature:
        return True
    if not (cfg.app_id and cfg.oa_secret_key):
        log.error("Thiếu ZALO_APP_ID/ZALO_OA_SECRET_KEY nên không xác thực được webhook")
        return False
    if not header:
        return False
    try:
        timestamp = str(json.loads(raw_body)["timestamp"])
    except (ValueError, KeyError, TypeError):
        return False
    data = raw_body.decode("utf-8")
    expected = hashlib.sha256(
        (cfg.app_id + data + timestamp + cfg.oa_secret_key).encode("utf-8")
    ).hexdigest()
    received = header.split("=", 1)[1] if header.startswith("mac=") else header
    return hmac.compare_digest(expected, received.strip())


class ZaloClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._token_file = cfg.data_dir / "tokens.json"
        self._load_tokens()

    # ---- token -------------------------------------------------------------
    def _load_tokens(self) -> None:
        # Refresh token của Zalo chỉ dùng được một lần, nên bản mới nhất nằm trong
        # file này chứ không phải biến môi trường ban đầu.
        if self._token_file.exists():
            saved = json.loads(self._token_file.read_text("utf-8"))
            self.cfg.access_token = saved.get("access_token") or self.cfg.access_token
            self.cfg.refresh_token = saved.get("refresh_token") or self.cfg.refresh_token

    def refresh_access_token(self) -> bool:
        if not (self.cfg.app_secret and self.cfg.refresh_token and self.cfg.app_id):
            return False
        body = urllib.parse.urlencode(
            {
                "refresh_token": self.cfg.refresh_token,
                "app_id": self.cfg.app_id,
                "grant_type": "refresh_token",
            }
        ).encode()
        req = urllib.request.Request(
            TOKEN_URL,
            data=body,
            headers={
                "secret_key": self.cfg.app_secret,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read())
        if "access_token" not in payload:
            log.error("Làm mới token thất bại: %s", payload)
            return False
        self.cfg.access_token = payload["access_token"]
        self.cfg.refresh_token = payload.get("refresh_token", self.cfg.refresh_token)
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        self._token_file.write_text(
            json.dumps(
                {"access_token": self.cfg.access_token, "refresh_token": self.cfg.refresh_token}
            ),
            "utf-8",
        )
        self._token_file.chmod(0o600)
        log.info("Đã làm mới access token")
        return True

    # ---- gửi tin -----------------------------------------------------------
    def _post_message(self, user_id: str, text: str) -> dict:
        body = json.dumps(
            {"recipient": {"user_id": user_id}, "message": {"text": text}}
        ).encode("utf-8")
        req = urllib.request.Request(
            SEND_URL,
            data=body,
            headers={"access_token": self.cfg.access_token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())

    def send_text(self, user_id: str, text: str) -> bool:
        if not self.cfg.access_token:
            log.warning("Chưa có ZALO_OA_ACCESS_TOKEN — chỉ ghi log, không gửi: %s", text[:60])
            return False
        with self._lock:
            result = self._post_message(user_id, text)
            # Mã lỗi token hết hạn/không hợp lệ: thử làm mới một lần rồi gửi lại.
            if result.get("error") in (-216, -124) and self.refresh_access_token():
                result = self._post_message(user_id, text)
        if result.get("error") != 0:
            log.error("Gửi tin cho %s thất bại: %s", user_id, result)
            return False
        return True

    # ---- ảnh ---------------------------------------------------------------
    @staticmethod
    def download_image(url: str, dest: Path) -> Path:
        """Tải ngay khi nhận — link ảnh của Zalo có thời hạn."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Ảnh vượt quá 15MB")
        dest.write_bytes(data)
        dest.chmod(0o600)
        return dest
