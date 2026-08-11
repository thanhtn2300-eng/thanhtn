"""Embedding + vector index + truy hồi có lọc metadata.

Index lưu dạng numpy (.npy) + metadata JSONL: đủ nhanh tới vài trăm nghìn chunk,
không cần dựng thêm service. Muốn đổi sang FAISS/Qdrant chỉ cần thay lớp
VectorIndex, phần embedder và filter giữ nguyên.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from .parser import _norm

log = logging.getLogger(__name__)

# Model mặc định: bi-encoder huấn luyện cho tiếng Việt. Model đa ngữ chung
# thường kém hẳn trên văn phong pháp lý tiếng Việt.
DEFAULT_MODEL = "bkai-foundation-models/vietnamese-bi-encoder"


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = 32):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.batch_size = batch_size
        self.name = model_name

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self.model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                show_progress_bar=len(texts) > 200,
            ),
            dtype=np.float32,
        )


class HashingEmbedder:
    """Embedder không cần tải model — dùng để test pipeline và chạy offline.

    Chất lượng truy hồi kém hơn hẳn model thật; chỉ dùng để kiểm tra đường ống.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in _norm(text).split():
                out[i, hash(token) % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norms, 1e-9)


def get_embedder(name: str = "auto"):
    if name == "hashing":
        return HashingEmbedder()
    try:
        return SentenceTransformerEmbedder(DEFAULT_MODEL if name == "auto" else name)
    except ImportError:
        if name != "auto":
            raise
        log.warning(
            "Chưa cài sentence-transformers — tạm dùng HashingEmbedder. "
            "Chất lượng truy hồi sẽ kém; cài bằng: pip install sentence-transformers"
        )
        return HashingEmbedder()


def _matches(meta: dict, filters: dict) -> bool:
    """Lọc metadata trước khi xếp hạng."""
    status = filters.get("tinh_trang")
    if status and _norm(status) not in _norm(meta.get("tinh_trang", "")):
        return False
    if filters.get("loai_van_ban") and _norm(filters["loai_van_ban"]) not in _norm(
        meta.get("loai_van_ban", "")
    ):
        return False
    if filters.get("item_ids") and meta.get("item_id") not in filters["item_ids"]:
        return False
    return True


class VectorIndex:
    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        self.vectors: np.ndarray | None = None
        self.metadata: list[dict] = []

    @property
    def _vec_path(self) -> Path:
        return self.dir / "vectors.npy"

    @property
    def _meta_path(self) -> Path:
        return self.dir / "metadata.jsonl"

    def build(self, chunks: list[dict], embedder) -> None:
        texts = [c["text"] for c in chunks]
        log.info("Đang embed %d chunk bằng %s ...", len(texts), embedder.name)
        self.vectors = embedder.encode(texts)
        self.metadata = chunks
        self.save()

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        np.save(self._vec_path, self.vectors)
        with self._meta_path.open("w", encoding="utf-8") as f:
            for m in self.metadata:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        log.info("Đã lưu index -> %s", self.dir)

    def load(self) -> "VectorIndex":
        if not self._vec_path.exists():
            raise FileNotFoundError(f"Chưa có index tại {self.dir}. Chạy lệnh `index` trước.")
        self.vectors = np.load(self._vec_path)
        self.metadata = [json.loads(l) for l in self._meta_path.read_text(encoding="utf-8").splitlines()]
        return self

    def search(self, query: str, embedder, top_k: int = 5, **filters) -> list[dict]:
        if self.vectors is None:
            self.load()
        query_vec = embedder.encode([query])[0]
        scores = self.vectors @ query_vec

        # Lọc metadata TRƯỚC khi lấy top-k: nếu lọc sau, văn bản hết hiệu lực
        # chiếm hết slot rồi mới bị loại, kết quả trả về sẽ thiếu.
        active = [i for i, m in enumerate(self.metadata) if _matches(m, filters)]
        if not active:
            return []
        active_arr = np.asarray(active)
        ranked = active_arr[np.argsort(-scores[active_arr])[:top_k]]

        return [{**self.metadata[i], "score": float(scores[i])} for i in ranked]
