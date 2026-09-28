import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tammi_oa import messages
from tammi_oa.config import Config
from tammi_oa.handler import Handler, wants_guide
from tammi_oa.server import make_server
from tammi_oa.store import Store
from tammi_oa.zalo import verify_signature


class FakeZalo:
    def __init__(self):
        self.sent = []

    def send_text(self, user_id, text):
        self.sent.append((user_id, text))
        return True

    def download_image(self, url, dest):
        if "hong" in url:
            raise OSError("404")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"jpg")
        return dest


def image_event(msg_id, user="u1", urls=("https://img/1.jpg",), text=""):
    return {
        "app_id": "app",
        "event_name": "user_send_image",
        "sender": {"id": user},
        "recipient": {"id": "oa"},
        "timestamp": "1700000000000",
        "message": {
            "msg_id": msg_id,
            "text": text,
            "attachments": [{"type": "image", "payload": {"url": u}} for u in urls],
        },
    }


class HandlerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(data_dir=Path(self.tmp.name))
        self.store = Store(self.cfg.db_path)
        self.zalo = FakeZalo()
        self.h = Handler(self.cfg, self.store, self.zalo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_and_later_image_get_different_replies(self):
        self.h.process(image_event("m1"))
        self.h.process(image_event("m2"))
        self.assertEqual(
            [t for _, t in self.zalo.sent],
            [messages.DA_NHAN_ANH_LAN_DAU, messages.DA_NHAN_ANH_LAN_SAU],
        )
        self.assertTrue(Path(self.store.list()[0]["local_path"]).exists())

    def test_webhook_retry_is_not_counted_or_thanked_twice(self):
        self.h.process(image_event("m1"))
        self.h.process(image_event("m1"))
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(len(self.zalo.sent), 1)

    def test_multiple_images_in_one_message(self):
        self.h.process(image_event("m1", urls=("https://a", "https://b")))
        self.assertEqual(len(self.store.list()), 2)
        self.assertEqual(len(self.zalo.sent), 1)

    def test_broken_image_link_still_recorded(self):
        self.h.process(image_event("m1", urls=("https://hong",)))
        row = self.store.list()[0]
        self.assertIsNone(row["local_path"])
        self.assertEqual(row["image_url"], "https://hong")

    def test_stats_count_people_not_images(self):
        self.h.process(image_event("m1", user="a"))
        self.h.process(image_event("m2", user="a"))
        self.h.process(image_event("m3", user="b"))
        for mid in ("m1", "m2"):
            self.store.set_status(mid, "hop_le")
        self.store.set_status("m3", "khong_hop_le", "ảnh mờ")
        s = self.store.stats()
        self.assertEqual(s["tong_anh"], 3)
        self.assertEqual(s["so_nguoi_hop_le"], 1)
        self.assertEqual(s["so_nguoi_da_gui"], 2)

    def test_text_keyword_sends_guide_and_name_is_kept(self):
        self.h.process({"event_name": "user_send_text", "sender": {"id": "u1"},
                        "message": {"text": "Hướng dẫn cài CHỮ KÝ SỐ"}})
        self.h.process({"event_name": "user_send_text", "sender": {"id": "u1"},
                        "message": {"text": "Nguyễn Văn A - Tổ 5"}})
        self.assertEqual(self.zalo.sent, [("u1", messages.HUONG_DAN)])
        self.h.process(image_event("m1"))
        self.assertEqual(self.store.list()[0]["last_text"], "Nguyễn Văn A - Tổ 5")

    def test_follow_sends_welcome(self):
        self.h.process({"event_name": "follow", "follower": {"id": "u9"}})
        self.assertEqual(self.zalo.sent, [("u9", messages.CHAO_MUNG)])

    def test_export_csv(self):
        self.h.process(image_event("m1"))
        out = Path(self.tmp.name) / "r.csv"
        self.assertEqual(self.store.export_csv(out), 1)
        self.assertIn("m1", out.read_text("utf-8-sig"))


class KeywordTest(unittest.TestCase):
    def test_keywords(self):
        self.assertTrue(wants_guide("hd"))
        self.assertTrue(wants_guide("Chữ ký số là gì?"))
        self.assertFalse(wants_guide("Nguyễn Văn Thắng - Tổ 3"))


class SignatureTest(unittest.TestCase):
    def test_valid_and_tampered(self):
        cfg = Config(app_id="app", oa_secret_key="secret")
        body = json.dumps({"timestamp": "123", "event_name": "x"}).encode()
        mac = hashlib.sha256(b"app" + body + b"123" + b"secret").hexdigest()
        self.assertTrue(verify_signature(cfg, body, f"mac={mac}"))
        self.assertFalse(verify_signature(cfg, body + b" ", f"mac={mac}"))
        self.assertFalse(verify_signature(cfg, body, None))

    def test_missing_secret_rejects(self):
        self.assertFalse(verify_signature(Config(), b'{"timestamp":"1"}', "mac=x"))


class ServerTest(unittest.TestCase):
    def test_end_to_end_over_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(app_id="app", oa_secret_key="secret", data_dir=Path(tmp), port=0)
            store, zalo = Store(cfg.db_path), FakeZalo()
            httpd = make_server(cfg, Handler(cfg, store, zalo))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            url = f"http://127.0.0.1:{httpd.server_address[1]}/webhook"
            body = json.dumps(image_event("m1")).encode()
            mac = hashlib.sha256(b"app" + body + b"1700000000000" + b"secret").hexdigest()
            try:
                with self.assertRaises(urllib.error.HTTPError) as err:
                    urllib.request.urlopen(urllib.request.Request(url, data=body))
                self.assertEqual(err.exception.code, 401)

                req = urllib.request.Request(url, data=body, headers={"X-ZEvent-Signature": f"mac={mac}"})
                self.assertEqual(urllib.request.urlopen(req).status, 200)
                for _ in range(50):  # xử lý chạy ở luồng nền
                    if zalo.sent:
                        break
                    threading.Event().wait(0.05)
                self.assertEqual(len(store.list()), 1)
            finally:
                httpd.shutdown()


if __name__ == "__main__":
    unittest.main()
