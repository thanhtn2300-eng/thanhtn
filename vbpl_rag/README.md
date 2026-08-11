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

Crawl → xuất dữ liệu → tạo chunk:

```bash
python -m vbpl.cli crawl --keyword "đầu tư" --max-pages 5
python -m vbpl.cli export --out data/documents.jsonl
python -m vbpl.cli chunk  --out data/chunks.jsonl --max-chars 1800
```

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

Logic parse và chunk đã được test trên HTML mẫu. **Chưa chạy được với vbpl.vn
thật** vì môi trường tạo repo này chặn outbound tới vbpl.vn — hãy chạy `probe`
ở máy bạn và báo lại output nếu selector cần chỉnh.
