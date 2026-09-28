"""HTTP server nhận webhook Zalo OA. Chỉ dùng thư viện chuẩn.

Zalo cần phản hồi 200 nhanh, nên server trả lời ngay rồi xử lý (tải ảnh, gửi tin)
ở luồng nền. Đặt sau reverse proxy có HTTPS (nginx, Cloudflare Tunnel...) vì Zalo
chỉ gọi webhook qua HTTPS.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .handler import Handler
from .store import Store
from .zalo import ZaloClient, verify_signature

log = logging.getLogger(__name__)
MAX_BODY = 1024 * 1024


def make_server(cfg: Config, handler: Handler) -> ThreadingHTTPServer:
    class Webhook(BaseHTTPRequestHandler):
        def _reply(self, code: int, body: str = "ok") -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            # Zalo kiểm tra URL webhook bằng GET khi đăng ký.
            self._reply(200 if self.path.split("?")[0] in ("/webhook", "/health") else 404)

        def do_POST(self):  # noqa: N802
            if self.path.split("?")[0] != "/webhook":
                return self._reply(404, "not found")
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._reply(400, "bad request")
            raw = self.rfile.read(length)
            if not verify_signature(cfg, raw, self.headers.get("X-ZEvent-Signature")):
                log.warning("Chữ ký webhook không hợp lệ từ %s", self.client_address[0])
                return self._reply(401, "invalid signature")
            try:
                event = json.loads(raw)
            except ValueError:
                return self._reply(400, "bad json")
            self._reply(200)
            threading.Thread(target=_safe_process, args=(handler, event), daemon=True).start()

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

    return ThreadingHTTPServer(("0.0.0.0", cfg.port), Webhook)


def _safe_process(handler: Handler, event: dict) -> None:
    try:
        handler.process(event)
    except Exception:
        log.exception("Lỗi xử lý sự kiện %s", event.get("event_name"))


def serve(cfg: Config) -> None:
    store = Store(cfg.db_path)
    handler = Handler(cfg, store, ZaloClient(cfg))
    httpd = make_server(cfg, handler)
    log.info("Tammi OA webhook đang chạy ở cổng %s (POST /webhook)", cfg.port)
    if not cfg.verify_signature:
        log.warning("ĐANG TẮT xác thực chữ ký — chỉ dùng để thử trên máy")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
