"""CLI: crawl / probe / export / chunk."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .chunk import chunk_document
from .client import ClientConfig, VbplClient
from .crawl import crawl, fetch_document, search_url
from .parser import parse_search_results, parse_total_pages
from .store import Store


def _client(args) -> VbplClient:
    return VbplClient(ClientConfig(delay=args.delay))


def cmd_probe(args) -> None:
    """Kiểm chứng selector trên HTML thật trước khi crawl hàng loạt."""
    client = _client(args)
    if args.item_id:
        doc = fetch_document(client, args.item_id)
        data = doc.to_dict()
        data["noi_dung"] = data["noi_dung"][:1500] + " ...(cắt bớt)"
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        html = client.get(search_url(1, args.row_count, Keyword=args.keyword)).text
        if args.dump_html:
            Path(args.dump_html).write_text(html, encoding="utf-8")
            print(f"Đã ghi HTML -> {args.dump_html}")
        results = parse_search_results(html)
        print(f"Tổng số trang đoán được: {parse_total_pages(html)}")
        print(f"Số kết quả trang 1: {len(results)}")
        for r in results[:10]:
            print(f"  {r['item_id']}  {r['tieu_de'][:90]}")


def cmd_crawl(args) -> None:
    store = Store(args.db)
    stats = crawl(
        store,
        _client(args),
        max_pages=args.max_pages,
        row_count=args.row_count,
        resume=not args.no_resume,
        Keyword=args.keyword,
        FromDate=args.from_date,
        ToDate=args.to_date,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Tổng văn bản trong DB: {store.count()}")


def cmd_export(args) -> None:
    store = Store(args.db)
    n = store.export_jsonl(args.out)
    print(f"Đã xuất {n} văn bản -> {args.out}")


def cmd_chunk(args) -> None:
    store = Store(args.db)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with out.open("w", encoding="utf-8") as f:
        for doc in store.iter_documents():
            for c in chunk_document(doc, args.max_chars, args.overlap):
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
                total += 1
    print(f"Đã tạo {total} chunk -> {out}")


def main() -> None:
    p = argparse.ArgumentParser(prog="vbpl", description="Crawler vbpl.vn cho RAG")
    p.add_argument("--db", default="data/vbpl.sqlite")
    p.add_argument("--delay", type=float, default=1.5, help="giây giữa 2 request")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe", help="thử 1 văn bản / 1 trang tìm kiếm")
    sp.add_argument("--item-id")
    sp.add_argument("--keyword", default="")
    sp.add_argument("--row-count", type=int, default=20)
    sp.add_argument("--dump-html")
    sp.set_defaults(func=cmd_probe)

    sc = sub.add_parser("crawl", help="crawl hàng loạt")
    sc.add_argument("--keyword", default="")
    sc.add_argument("--from-date", default="", help="dd/mm/yyyy")
    sc.add_argument("--to-date", default="", help="dd/mm/yyyy")
    sc.add_argument("--max-pages", type=int)
    sc.add_argument("--row-count", type=int, default=20)
    sc.add_argument("--no-resume", action="store_true")
    sc.set_defaults(func=cmd_crawl)

    se = sub.add_parser("export", help="xuất JSONL toàn văn")
    se.add_argument("--out", default="data/documents.jsonl")
    se.set_defaults(func=cmd_export)

    sk = sub.add_parser("chunk", help="tạo chunk cho RAG")
    sk.add_argument("--out", default="data/chunks.jsonl")
    sk.add_argument("--max-chars", type=int, default=1800)
    sk.add_argument("--overlap", type=int, default=150)
    sk.set_defaults(func=cmd_chunk)

    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
