# vbpl-rag — thu thập văn bản pháp luật từ vbpl.vn cho RAG

## vbpl.vn có API không?

**Không có REST/JSON API công khai.** vbpl.vn (Cơ sở dữ liệu quốc gia về văn bản
pháp luật) là site ASP.NET render HTML phía server. Cách lấy dữ liệu là scrape 3 trang:

| Mục đích | Đường dẫn |
|---|---|
| Tìm kiếm / danh sách | `/TW/Pages/vbpq-timkiem.aspx?dvid=13&Page=1&RowCount=20&Keyword=...` |
| Thuộc tính văn bản | `/TW/Pages/vbpq-thuoctinh.aspx?ItemID=<id>` |
| Toàn văn | `/TW/Pages/vbpq-toanvan.aspx?ItemID=<id>` |
| Lược đồ / văn bản liên quan | `/TW/Pages/vbpq-luocdo.aspx?ItemID=<id>` |

`ItemID` là khoá chính của một văn bản, xuất hiện trong link ở trang tìm kiếm.
`dvid=13` là nhánh Trung ương; các nhánh địa phương dùng prefix và dvid khác.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Dùng

Luôn chạy `probe` trước để kiểm chứng selector trên HTML thật:

```bash
python -m vbpl.cli probe --keyword "đầu tư công"        # thử trang tìm kiếm
python -m vbpl.cli probe --item-id 139264               # thử 1 văn bản
python -m vbpl.cli probe --keyword "" --dump-html /tmp/search.html   # lưu HTML để soi
```

### Bộ lọc

Tất cả tham số lọc nằm trong `SearchFilters` (`vbpl/filters.py`), render ra được
hai dạng: query-string cho trang HTML (`to_query_params`) và JSON body
(`to_json_body`, dùng tên trường `keyword / docType / agencyIds / fieldTypeIds /
effStatus / fromDate / toDate / page / pageSize`). Đổi backend chỉ sửa một chỗ.

```bash
python -m vbpl.cli crawl \
  --keyword "đầu tư công" \
  --doc-type 22 --agency-ids 1,5 --field-type-ids 3 \
  --eff-status con-hieu-luc \
  --from-date 01/01/2020 --to-date 31/12/2024 \
  --row-count 50 --max-pages 10
```

`--eff-status con-hieu-luc` nên là mặc định khi build RAG. Ngày sai định dạng
hoặc eff-status không hợp lệ bị chặn ngay lúc dựng bộ lọc, không đợi tới lúc
request trả về kết quả rỗng khó hiểu.

### Dùng endpoint JSON thay vì scrape HTML

```bash
export VBPL_API_BASE="https://<host>/<đường-dẫn-tìm-kiếm>"   # bắt buộc
export VBPL_API_KEY="<key 40 ký tự>"                          # bắt buộc
export VBPL_API_AUTH="bearer"      # bearer | x-api-key | query | path
export VBPL_API_METHOD="POST"      # POST | GET

python -m vbpl.cli crawl --api --keyword "đầu tư công" --eff-status con-hieu-luc
```

Key đọc từ biến môi trường, **không commit vào repo**. Cách truyền key và schema
response chưa xác minh được với API thật, nên `--api` thử lần lượt các khoá phổ
biến (`items/data/results`, `ItemID/id`, `totalCount/total`) và báo rõ khoá nào
có trong response nếu không khớp — đổi `VBPL_API_AUTH` là thử được kiểu khác mà
không phải sửa code.

### Chạy cả pipeline một lượt

```bash
python -m vbpl.cli pipeline \
  --keyword "đầu tư công" --eff-status con-hieu-luc --max-pages 10 \
  --with-attachments --index-dir data/index
```

Tương đương chạy lần lượt:

```bash
python -m vbpl.cli crawl    --keyword "đầu tư" --max-pages 5   # tải văn bản về SQLite
python -m vbpl.cli download --out-dir data/files               # tải PDF/DOC đính kèm
python -m vbpl.cli index    --index-dir data/index             # embed + dựng vector index
python -m vbpl.cli search   "điều kiện đầu tư kinh doanh"      # truy hồi thử
python -m vbpl.cli export   --out data/documents.jsonl         # xuất JSONL nếu cần
```

`download` còn dùng để **vá dữ liệu thiếu**: văn bản nào có toàn văn rỗng hoặc quá
ngắn (bản scan) thì rút text từ tệp đính kèm để thay vào. Không có bước này, những
văn bản đó biến mất khỏi RAG.

### Nội dung ở dạng Markdown

`fetch_document` **thử JSON trước** (gửi `Accept: application/json`), lùi về parse
HTML nếu server trả HTML — nên không cần biết trước site trả kiểu gì.

Nội dung luôn được chuyển sang **Markdown**, không phải text phẳng:

- JSON/HTML từ web → `markdownify`
- PDF/DOCX đính kèm → `markitdown`

Lý do: text phẳng làm **nát bảng biểu** (biểu phí, phụ lục, danh mục) — mất bảng
là mất luôn khả năng trả lời đúng những câu hỏi về mức phí, hạn mức, danh mục.
Đã kiểm chứng: cùng một bảng HTML, đường text phẳng cho ra `STT / Mức phí / 1 /
500.000đ` rời rạc, còn đường Markdown giữ nguyên `| STT | Mức phí |`.

Chunker nhận diện `Điều` kể cả khi nó là heading Markdown (`### Điều 1.`,
`**Điều 1.**`) hay text thuần.

Thiếu `markdownify`/`markitdown` thì vẫn chạy được (tự lùi về rút text thô) nhưng
mất bảng — log sẽ cảnh báo một lần.

### Truy hồi

`search` mặc định **chỉ trả về văn bản còn hiệu lực** (`--tinh-trang "con hieu luc"`,
truyền `""` để bỏ lọc). Bộ lọc chạy *trước* khi xếp hạng top-k, nếu không văn bản
hết hiệu lực sẽ chiếm slot rồi mới bị loại và kết quả trả về bị thiếu.

Đây không phải chi tiết nhỏ. Test trên dữ liệu mẫu: cùng một câu hỏi, khi bỏ lọc
thì Luật Đầu tư 2014 (đã hết hiệu lực) xếp **hạng 1**, đẩy Luật Đầu tư 2020 xuống
hạng 2 — tức là hệ thống sẽ trả lời theo luật đã bị thay thế.

Embedder mặc định là `bkai-foundation-models/vietnamese-bi-encoder`. Chưa cài
`sentence-transformers` thì tự lùi về `hashing` (chạy được ngay, chất lượng kém —
chỉ nên dùng để kiểm tra đường ống).

Crawl có **resume**: đã lưu trong SQLite thì bỏ qua, nên cứ Ctrl-C rồi chạy lại.
Văn bản lỗi được ghi vào bảng `failures` chứ không làm chết cả job.

## Thiết kế chunk

Cắt theo **Điều** (kèm ngữ cảnh Chương/Mục) thay vì cắt theo số ký tự cố định:
một Điều là đơn vị trích dẫn tự nhiên, giữ nguyên thì câu trả lời của RAG mới
trích được đúng "Điều X của <số ký hiệu>" để người dùng kiểm chứng. Điều nào quá
dài mới cắt tiếp theo đoạn/câu, có overlap.

Mỗi chunk mang metadata: `item_id, so_ky_hieu, loai_van_ban, co_quan_ban_hanh,
ngay_ban_hanh, ngay_hieu_luc, tinh_trang, chuong, muc, dieu, url`.

`tinh_trang` (còn/hết hiệu lực) là trường quan trọng nhất khi lọc: **phải lọc
văn bản hết hiệu lực ra khỏi kết quả truy hồi**, nếu không hệ thống sẽ trả lời
theo quy định đã bị thay thế.

## Lưu ý vận hành

- Mặc định delay 1.5s/request. Đừng hạ xuống thấp — site không dành cho tải cao,
  và bạn sẽ bị chặn IP.
- Kiểm tra `robots.txt` và điều khoản sử dụng của vbpl.vn trước khi crawl diện rộng.
- Selector HTML có thể đổi khi site cập nhật. Các hàm parse đều có fallback
  heuristic và không ném lỗi khi thiếu trường, nhưng nếu `probe` trả về nội dung
  rỗng thì cần chỉnh lại danh sách selector trong `vbpl/parser.py`.

## Trạng thái kiểm thử

Đã test: parse HTML (trên HTML mẫu), chunk theo Điều, bộ lọc tìm kiếm, backend
JSON (trên mock server), embed → index → search có lọc hiệu lực (end-to-end trên
dữ liệu mẫu).

**Chưa chạy được với vbpl.vn thật** vì môi trường tạo repo này chặn outbound tới
vbpl.vn. Hai thứ chỉ lộ ra khi chạy máy bạn:

1. **Selector HTML** — chạy `probe --item-id <id>`; nếu `noi_dung` rỗng thì sửa
   danh sách selector trong `vbpl/parser.py`.
2. **Tên tham số lọc phía HTML** (`type`, `organ`, `field`, `EffectStatus`) là
   suy đoán theo quy ước site; `probe` in ra URL đầy đủ để bạn đối chiếu với URL
   thật trên trình duyệt.

Với `--api`: nếu 401 thì đổi `VBPL_API_AUTH`; nếu schema response không khớp,
lỗi sẽ in ra đúng danh sách khoá API trả về để map lại trong `vbpl/api.py`.
