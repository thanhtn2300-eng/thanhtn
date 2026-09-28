# Chiến dịch "Cài chữ ký số trên VNeID" qua Tammi OA

| Tệp | Dùng để |
|---|---|
| [`truyen-thong.md`](truyen-thong.md) | Bộ nội dung: thông điệp, hướng dẫn, mẫu bài Zalo/Facebook, loa phát thanh, poster, lịch 4 tuần, hỏi đáp |
| `tammi_oa/` | Bot webhook Zalo OA: nhận ảnh người dân gửi, tự trả lời, lưu lại để duyệt và thống kê |

## Luồng hoạt động

```
Người dân ── ảnh chụp màn hình ──▶ khung chat Tammi OA (Zalo)
                                      │ webhook user_send_image
                                      ▼
                               tammi_oa (server này)
                               ├─ tải ảnh ngay (link Zalo có hạn)
                               ├─ lưu SQLite, chống trùng theo msg_id
                               └─ trả lời "✅ Tammi đã nhận ảnh"
                                      │
Cán bộ ◀── list / duyet / stats / export ──┘
```

Ngoài ảnh, bot còn:

- **follow** (người dân bấm Quan tâm): gửi lời chào kèm hướng dẫn.
- **tin nhắn có từ khoá** (`hd`, `hướng dẫn`, `chữ ký số`...): gửi hướng dẫn.
- **tin nhắn khác** (thường là "Họ tên – Tổ 5"): chỉ lưu để đối chiếu khi duyệt, không
  tự trả lời. Cán bộ vẫn trò chuyện trực tiếp trên OA như bình thường.

Nội dung tin nhắn tự động nằm trong `tammi_oa/messages.py`, sửa chữ ở đó.

## Không muốn chạy server?

Chiến dịch nhỏ (vài trăm người) làm tay trên **OA Manager** là đủ: cài *Tin nhắn tự
động theo từ khoá* với nội dung giống `messages.py`, rồi cán bộ đếm ảnh trong khung
chat. Bot đáng dựng khi lượng ảnh lớn, cần chống trùng, duyệt và xuất báo cáo theo tổ.

## Cài đặt

Chỉ dùng thư viện chuẩn Python ≥ 3.10, không có dependency.

1. **developers.zalo.me** → tạo ứng dụng, liên kết với Tammi OA, cấp quyền gửi tin
   và nhận sự kiện.
2. Mục **Webhook**: điền URL `https://<tên-miền>/webhook`, bật các sự kiện
   `user_send_image`, `user_send_text`, `follow`. Lấy **OA Secret Key**.
3. Lấy **access token** (và refresh token) của OA.
4. Chạy:

```bash
cd vneid_campaign
export ZALO_APP_ID="..."
export ZALO_OA_SECRET_KEY="..."
export ZALO_OA_ACCESS_TOKEN="..."
# tuỳ chọn, để bot tự làm mới token khi hết hạn (khoảng 25 giờ):
export ZALO_APP_SECRET="..."
export ZALO_REFRESH_TOKEN="..."

python -m tammi_oa.cli serve          # lắng nghe cổng 8080 (TAMMI_PORT)
```

Zalo chỉ gọi webhook qua **HTTPS**, nên đặt server sau nginx/Caddy có chứng chỉ,
hoặc dùng Cloudflare Tunnel.

Token, secret đọc từ biến môi trường, **không commit vào repo**. Refresh token của
Zalo chỉ dùng được một lần, nên sau lần làm mới đầu tiên bản mới nhất nằm trong
`data/tokens.json` (quyền 600), không còn ở biến môi trường.

## Vận hành hằng ngày

```bash
python -m tammi_oa.cli list --status cho_duyet           # ảnh chờ duyệt (đường dẫn tới file ảnh)
python -m tammi_oa.cli duyet <msg_id> hop_le
python -m tammi_oa.cli duyet <msg_id> khong_hop_le --note "ảnh mờ"
python -m tammi_oa.cli stats                             # số NGƯỜI hợp lệ, không phải số ảnh
python -m tammi_oa.cli export --out bao_cao.csv          # mở bằng Excel, đúng dấu tiếng Việt
```

`stats` đếm **số người khác nhau** có ảnh hợp lệ. Một người gửi 3 ảnh vẫn tính là 1,
vì chỉ tiêu chiến dịch là số người đã cài. Cột `tin_nhan_gan_nhat` trong CSV chứa
"Họ tên – Tổ" người dân nhắn, dùng để lọc theo tổ trong Excel.

## Dữ liệu cá nhân

- Ảnh lưu tại `data/anh/<zalo_user_id>/` với quyền 600. Thư mục `data/` đã nằm trong
  `.gitignore`, **không bao giờ commit**.
- Hết chiến dịch: `export` số liệu, rồi **xoá `data/anh/`**.
- Xem thêm mục 9 trong `truyen-thong.md`.

## Kiểm thử

```bash
cd vneid_campaign
python -m unittest discover -s tests -v
```

Bộ test (không cần mạng, Zalo được giả lập) bao gồm: xác thực chữ ký webhook, ảnh
đầu/ảnh sau nhận lời trả khác nhau, webhook gửi lặp không bị đếm hay cảm ơn hai lần,
nhiều ảnh trong một tin, link ảnh hỏng vẫn giữ bản ghi, thống kê đếm theo người, từ
khoá tiếng Việt có/không dấu, xuất CSV, và chạy qua HTTP thật từ đầu đến cuối.

**Chưa chạy với Tammi OA thật** vì môi trường tạo repo này không có tài khoản Zalo.
Ba thứ cần kiểm tra khi thử lần đầu:

1. **Chữ ký webhook.** Nếu mọi request bị `401 invalid signature`, đối chiếu công
   thức `sha256(app_id + body + timestamp + oa_secret_key)` trong `tammi_oa/zalo.py`
   với tài liệu Zalo hiện hành. Có thể tạm đặt `TAMMI_VERIFY_SIGNATURE=0` để xem
   payload thật, nhưng **bật lại ngay**.
2. **Gửi tin.** Log `Gửi tin ... thất bại` sẽ in nguyên phản hồi của Zalo. Lỗi hay
   gặp là token hết hạn hoặc OA chưa được cấp quyền gửi tin tư vấn.
3. **Người dân gửi ảnh dạng file** (sự kiện `user_send_file`) hiện chưa được xử lý.
   Nếu gặp nhiều thì bổ sung nhánh trong `tammi_oa/handler.py`.
