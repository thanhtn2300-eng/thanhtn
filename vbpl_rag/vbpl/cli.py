"""CLI: crawl / probe / export / chunk."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .chunk import chunk_document
from .client import ClientConfig, VbplClient
from .crawl import crawl, fetch_document, search_url
from .filters import EFF_STATUS, SearchFilters
from .parser import parse_search_results, parse_total_pages
from .store import Store


def _client(args) -> VbplClient:
    return VbplClient(ClientConfig(delay=args.delay))


def _ids(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _filters(args) -> SearchFilters:
    return SearchFilters(
        keyword=getattr(args, "keyword", "") or "",
        doc_type=getattr(args, "doc_type", None),
        agency_ids=_ids(getattr(args, "agency_ids", "")),
        field_type_ids=_ids(getattr(args, "field_type_ids", "")),
        eff_status=getattr(args, "eff_status", None),
        from_date=getattr(args, "from_date", "") or "",
        to_date=getattr(args, "to_date", "") or "",
        row_count=getattr(args, "row_count", 20),
    )


def _add_filter_args(parser) -> None:
    parser.add_argument("--keyword", default="")
    parser.add_argument("--doc-type", help="id loại văn bản (Luật, Nghị định, Thông tư...)")
    parser.add_argument("--agency-ids", default="", help="id cơ quan ban hành, phân tách bằng dấu phẩy")
    parser.add_argument("--field-type-ids", default="", help="id lĩnh vực, phân tách bằng dấu phẩy")
    parser.add_argument(
        "--eff-status",
        choices=sorted(EFF_STATUS),
        help="trạng thái hiệu lực — nên đặt 'con-hieu-luc' khi build RAG",
    )
    parser.add_argument("--from-date", default="", help="dd/mm/yyyy")
    parser.add_argument("--to-date", default="", help="dd/mm/yyyy")
    parser.add_argument("--row-count", type=int, default=20)


def _add_chunk_args(parser) -> None:
    parser.add_argument("--max-chars", type=int, default=1800)
    parser.add_argument("--overlap", type=int, default=150)


def _add_index_args(parser) -> None:
    parser.add_argument("--index-dir", default="data/index")
    parser.add_argument(
        "--embedder",
        default="auto",
        help="'auto' (model tiếng Việt), 'hashing' (không cần tải model), hoặc tên model",
    )


def cmd_probe(args) -> None:
    """Kiểm chứng selector trên HTML thật trước khi crawl hàng loạt."""
    client = _client(args)
    if args.item_id:
        doc = fetch_document(client, args.item_id)
        data = doc.to_dict()
        data["noi_dung"] = data["noi_dung"][:1500] + " ...(cắt bớt)"
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        filters = _filters(args)
        url = search_url(filters)
        print(f"URL: {url}")
        html = client.get(url).text
        if args.dump_html:
            Path(args.dump_html).write_text(html, encoding="utf-8")
            print(f"Đã ghi HTML -> {args.dump_html}")
        results = parse_search_results(html)
        print(f"Tổng số trang đoán được: {parse_total_pages(html)}")
        print(f"Số kết quả trang 1: {len(results)}")
        for r in results[:10]:
            print(f"  {r['item_id']}  {r['tieu_de'][:90]}")


def _backend(args, client):
    if not getattr(args, "api", False):
        return None
    from .api import JsonSearchBackend

    return JsonSearchBackend(client)


def cmd_crawl(args) -> None:
    store = Store(args.db)
    client = _client(args)
    stats = crawl(
        store,
        client,
        _filters(args),
        max_pages=args.max_pages,
        resume=not args.no_resume,
        backend=_backend(args, client),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Tổng văn bản trong DB: {store.count()}")


def cmd_download(args) -> None:
    from .download import download_attachments
    from .markdown import file_to_markdown

    store = Store(args.db)
    client = _client(args)
    files = filled = 0
    for doc in store.iter_documents():
        for path in download_attachments(client, doc, args.out_dir):
            files += 1
            # Toàn văn rỗng/quá ngắn thường là văn bản chỉ có bản scan hoặc file đính kèm.
            if len(doc.get("noi_dung", "")) < args.min_chars:
                text = file_to_markdown(path)
                if len(text) > len(doc.get("noi_dung", "")):
                    doc["noi_dung"] = text
                    _save_dict(store, doc)
                    filled += 1
    print(f"Đã tải {files} tệp, bổ sung nội dung cho {filled} văn bản")


def _save_dict(store: Store, doc: dict) -> None:
    from .parser import Document

    fields = {k: v for k, v in doc.items() if k in Document.__dataclass_fields__}
    store.save(Document(**fields))


def cmd_index(args) -> None:
    from .index import VectorIndex, get_embedder

    store = Store(args.db)
    chunks = []
    for doc in store.iter_documents():
        chunks.extend(chunk_document(doc, args.max_chars, args.overlap))
    if not chunks:
        print("Chưa có dữ liệu để index. Chạy `crawl` trước.")
        return
    VectorIndex(args.index_dir).build(chunks, get_embedder(args.embedder))
    print(f"Đã index {len(chunks)} chunk -> {args.index_dir}")


def cmd_search(args) -> None:
    from .index import VectorIndex, get_embedder

    index = VectorIndex(args.index_dir).load()
    hits = index.search(
        args.query,
        get_embedder(args.embedder),
        top_k=args.top_k,
        tinh_trang=args.tinh_trang,
        loai_van_ban=args.loai_van_ban,
    )
    if not hits:
        print("Không có kết quả khớp bộ lọc.")
        return
    for i, hit in enumerate(hits, 1):
        loc = " ".join(x for x in (hit.get("chuong"), hit.get("muc"), hit.get("dieu")) if x)
        print(f"\n[{i}] score={hit['score']:.3f}  {hit.get('so_ky_hieu')} — {hit.get('tieu_de')}")
        print(f"    {loc}  | {hit.get('tinh_trang')}  | {hit.get('url')}")
        print("    " + hit["text"][:300].replace("\n", " "))


def cmd_pipeline(args) -> None:
    """crawl -> (tuỳ chọn) tải đính kèm -> chunk -> index, chạy một lượt."""
    cmd_crawl(args)
    if args.with_attachments:
        cmd_download(args)
    cmd_index(args)


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
    sp.add_argument("--dump-html")
    _add_filter_args(sp)
    sp.set_defaults(func=cmd_probe)

    sc = sub.add_parser("crawl", help="crawl hàng loạt")
    sc.add_argument("--max-pages", type=int)
    sc.add_argument("--no-resume", action="store_true")
    sc.add_argument("--api", action="store_true", help="dùng endpoint JSON thay vì scrape HTML")
    _add_filter_args(sc)
    sc.set_defaults(func=cmd_crawl)

    se = sub.add_parser("export", help="xuất JSONL toàn văn")
    se.add_argument("--out", default="data/documents.jsonl")
    se.set_defaults(func=cmd_export)

    sk = sub.add_parser("chunk", help="tạo chunk cho RAG")
    sk.add_argument("--out", default="data/chunks.jsonl")
    _add_chunk_args(sk)
    sk.set_defaults(func=cmd_chunk)

    sd = sub.add_parser("download", help="tải tệp đính kèm, bổ sung nội dung còn thiếu")
    sd.add_argument("--out-dir", default="data/files")
    sd.add_argument("--min-chars", type=int, default=200, help="dưới ngưỡng này thì rút text từ file")
    sd.set_defaults(func=cmd_download)

    si = sub.add_parser("index", help="embed + dựng vector index")
    _add_chunk_args(si)
    _add_index_args(si)
    si.set_defaults(func=cmd_index)

    ss = sub.add_parser("search", help="truy hồi thử")
    ss.add_argument("query")
    ss.add_argument("--top-k", type=int, default=5)
    ss.add_argument("--tinh-trang", default="con hieu luc", help="'' để bỏ lọc hiệu lực")
    ss.add_argument("--loai-van-ban", default="")
    _add_index_args(ss)
    ss.set_defaults(func=cmd_search)

    spl = sub.add_parser("pipeline", help="crawl -> tải file -> chunk -> index, một lượt")
    spl.add_argument("--max-pages", type=int)
    spl.add_argument("--no-resume", action="store_true")
    spl.add_argument("--api", action="store_true")
    spl.add_argument("--with-attachments", action="store_true")
    spl.add_argument("--out-dir", default="data/files")
    spl.add_argument("--min-chars", type=int, default=200)
    _add_filter_args(spl)
    _add_chunk_args(spl)
    _add_index_args(spl)
    spl.set_defaults(func=cmd_pipeline)

    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
