"""Nội dung tin nhắn tự động của Tammi OA. Sửa chữ ở đây, không cần đụng code xử lý.

Giữ đúng nguyên tắc chống lừa đảo trong mọi tin: OA KHÔNG BAO GIỜ xin mật khẩu,
passcode, mã OTP hay ảnh CCCD — người dân được dặn như vậy từ bài truyền thông, tin
nhắn tự động mà lệch đi là mất lòng tin.
"""

HUONG_DAN = (
    "📌 Hướng dẫn gửi ảnh xác nhận đã cài chữ ký số VNeID:\n"
    "1. Mở VNeID, vào màn hình Chữ ký số đang hiển thị trạng thái ĐÃ KÍCH HOẠT.\n"
    "2. Chụp màn hình.\n"
    "3. Che/cắt số định danh, ngày sinh, mã QR trước khi gửi.\n"
    "4. Gửi ảnh vào khung chat này, kèm tin nhắn: Họ tên – Tổ/Khu phố.\n\n"
    "⚠️ Tammi OA KHÔNG BAO GIỜ hỏi mật khẩu, passcode, mã OTP hay ảnh CCCD. "
    "Ai hỏi những thông tin đó là lừa đảo."
)

CHAO_MUNG = "Cảm ơn bạn đã quan tâm Tammi OA! 🎉\n\n" + HUONG_DAN

DA_NHAN_ANH_LAN_DAU = (
    "✅ Tammi đã nhận ảnh của bạn, cảm ơn bạn đã cài chữ ký số trên VNeID!\n"
    "Nếu chưa nhắn, bạn gửi thêm giúp Tammi: Họ tên – Tổ/Khu phố để ghi nhận nhé.\n"
    "Nhắc lại: Tammi không bao giờ hỏi mật khẩu, passcode hay mã OTP."
)

DA_NHAN_ANH_LAN_SAU = "✅ Tammi đã nhận thêm ảnh của bạn. Cảm ơn bạn!"

# So khớp sau khi bỏ dấu và chuyển chữ thường.
TU_KHOA_HUONG_DAN = ("huong dan", "chu ky so", "cach gui", "ky so", "vneid", "hd")
