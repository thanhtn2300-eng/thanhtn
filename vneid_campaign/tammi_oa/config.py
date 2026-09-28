"""Cấu hình đọc từ biến môi trường — token/secret KHÔNG commit vào repo.

    export ZALO_APP_ID="..."             # ID ứng dụng trên developers.zalo.me
    export ZALO_OA_SECRET_KEY="..."      # "OA Secret Key" ở mục Webhook, dùng xác thực chữ ký
    export ZALO_OA_ACCESS_TOKEN="..."    # token để OA gửi tin trả lời
    export ZALO_APP_SECRET="..."         # tuỳ chọn: tự làm mới access token
    export ZALO_REFRESH_TOKEN="..."      # tuỳ chọn: đi kèm ZALO_APP_SECRET
    export TAMMI_DATA_DIR="data"         # nơi lưu ảnh + SQLite
    export TAMMI_PORT=8080
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    app_id: str = ""
    oa_secret_key: str = ""
    access_token: str = ""
    app_secret: str = ""
    refresh_token: str = ""
    data_dir: Path = Path("data")
    port: int = 8080
    # Tắt xác thực chữ ký chỉ để thử trên máy — webhook công khai thì phải bật.
    verify_signature: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            app_id=os.environ.get("ZALO_APP_ID", ""),
            oa_secret_key=os.environ.get("ZALO_OA_SECRET_KEY", ""),
            access_token=os.environ.get("ZALO_OA_ACCESS_TOKEN", ""),
            app_secret=os.environ.get("ZALO_APP_SECRET", ""),
            refresh_token=os.environ.get("ZALO_REFRESH_TOKEN", ""),
            data_dir=Path(os.environ.get("TAMMI_DATA_DIR", "data")),
            port=int(os.environ.get("TAMMI_PORT", "8080")),
            verify_signature=os.environ.get("TAMMI_VERIFY_SIGNATURE", "1") != "0",
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tammi.sqlite3"

    @property
    def image_dir(self) -> Path:
        return self.data_dir / "anh"
