"""Dòng lệnh cho cán bộ vận hành chiến dịch.

    python -m tammi_oa.cli serve                       # chạy webhook
    python -m tammi_oa.cli list --status cho_duyet     # xem ảnh chờ duyệt
    python -m tammi_oa.cli duyet <msg_id> hop_le       # hoặc khong_hop_le --note "..."
    python -m tammi_oa.cli stats                       # số người đã cài
    python -m tammi_oa.cli export --out bao_cao.csv    # xuất Excel/CSV
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import Config
from .server import serve
from .store import STATUSES, Store


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tammi_oa")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="chạy webhook nhận tin từ Zalo OA")
    ls = sub.add_parser("list", help="liệt kê ảnh đã nhận")
    ls.add_argument("--status", choices=STATUSES)
    dv = sub.add_parser("duyet", help="đánh dấu ảnh hợp lệ / không hợp lệ")
    dv.add_argument("msg_id")
    dv.add_argument("status", choices=STATUSES)
    dv.add_argument("--note", default="")
    sub.add_parser("stats", help="thống kê chiến dịch")
    ex = sub.add_parser("export", help="xuất CSV (mở được bằng Excel)")
    ex.add_argument("--out", type=Path, default=Path("bao_cao_chu_ky_so.csv"))
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.from_env()

    if args.cmd == "serve":
        serve(cfg)
        return 0

    store = Store(cfg.db_path)
    if args.cmd == "list":
        for r in store.list(args.status):
            print(
                f"{r['msg_id']}\t{r['received_at']}\t{r['status']}\t"
                f"{r['last_text'] or ''}\t{r['local_path'] or r['image_url']}"
            )
    elif args.cmd == "duyet":
        if not store.set_status(args.msg_id, args.status, args.note):
            print(f"Không tìm thấy msg_id {args.msg_id}")
            return 1
    elif args.cmd == "stats":
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
    elif args.cmd == "export":
        n = store.export_csv(args.out)
        print(f"Đã xuất {n} dòng ra {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
