"""
模块 13 · RAG 知识库（教务规章问答）
--------------------------------------------------------------------
作用：把 knowledge/ 目录下的教务规章 Markdown 切片、向量化、建索引；
      AI 回答「转专业要什么条件」「学分认定怎么弄」时先检索再作答，避免瞎编。
两种模式：
  1) 在线：调 embedding 模型（OpenAI 兼容接口），精度高；
  2) 离线：字符 n-gram + TF-IDF 余弦相似度（纯 numpy 实现），零依赖可跑。
"""

from __future__ import annotations

import asyncio
import math
import re
from collections import Counter
from pathlib import Path

from app.config import KB_DIR, settings

try:
    import numpy as np
except Exception:            # pragma: no cover - numpy 缺失时退回纯 Python
    np = None


def _tokens(text: str) -> list[str]:
    """11.1 中文友好分词：单字 + 相邻二字 + 英文数字词，不依赖 jieba。"""
    lowered = text.lower()
    chars = [c for c in lowered if not c.isspace()]
    uni = chars
    bi = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
    words = re.findall(r"[a-z0-9_]+", lowered)
    return uni + bi + words


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    """11.2 按空行分段后合并到 chunk_size 左右，保留段落语义。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) <= chunk_size or not buf:
            buf = (buf + "\n" + p) if buf else p
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


class KnowledgeBase:
    """11.3 轻量向量库：chunks 列表 + 归一化向量矩阵，内存搜索。"""

    def __init__(self) -> None:
        self.chunks: list[dict] = []
        self.matrix = None
        self.mode = "offline"
        self._lock = asyncio.Lock()
        self._ready = False

    async def ensure_loaded(self) -> None:
        async with self._lock:
            if self._ready:
                return
            self.chunks = self._load_chunks()
            if not self.chunks:
                self._ready = True
                return
            if settings.embeddings_online():
                try:
                    await asyncio.wait_for(self._build_online(), timeout=12)
                except Exception:
                    self._build_offline()      # 网络/接口不可用时秒级回退
            else:
                self._build_offline()
            self._ready = True

    # ---- 11.3.1 读取并切片 ----
    def _load_chunks(self) -> list[dict]:
        chunks: list[dict] = []
        if not KB_DIR.exists():
            return chunks
        for path in sorted(KB_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            title = path.stem
            for i, piece in enumerate(_chunk_text(text, settings.rag_chunk_size)):
                chunks.append({"title": title, "chunk_id": i, "content": piece})
        return chunks

    # ---- 11.3.2 在线向量化 ----
    async def _build_online(self) -> None:
        from langchain_openai import OpenAIEmbeddings

        emb = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            timeout=8,
        )
        vectors = await emb.aembed_documents([c["content"] for c in self.chunks])
        arr = np.array(vectors, dtype="float32")
        self.matrix = arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-8)
        self.mode = "online"

    # ---- 11.3.3 离线 TF-IDF ----
    def _build_offline(self) -> None:
        tokenized = [_tokens(c["content"]) for c in self.chunks]
        df: Counter = Counter()
        for toks in tokenized:
            df.update(set(toks))
        n = len(tokenized)
        vocab = {t: i for i, t in enumerate(sorted(df))}
        idf = [math.log((n + 1) / (df[t] + 1)) + 1 for t in vocab]
        rows = []
        for toks in tokenized:
            vec = [0.0] * len(vocab)
            counts = Counter(toks)
            for t, c in counts.items():
                idx = vocab.get(t)
                if idx is not None:
                    vec[idx] = (1 + math.log(c)) * idf[idx]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            rows.append([v / norm for v in vec])
        self._vocab = vocab
        self._idf = idf
        self.matrix = np.array(rows, dtype="float32") if np is not None else rows
        self.mode = "offline"

    async def search(self, query: str, k: int | None = None) -> list[dict]:
        """11.4 检索入口：返回 top-k 片段（带标题和分数）。"""
        await self.ensure_loaded()
        k = k or settings.rag_top_k
        if not self.chunks or self.matrix is None:
            return []
        if self.mode == "online":
            from langchain_openai import OpenAIEmbeddings

            emb = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.embedding_api_key,
                base_url=settings.embedding_base_url,
                timeout=8,
            )
            q = np.array(await emb.aembed_query(query), dtype="float32")
            q = q / (np.linalg.norm(q) + 1e-8)
            scores = self.matrix @ q
        else:
            scores = self._offline_scores(query)
        order = sorted(range(len(scores)), key=lambda i: float(scores[i]), reverse=True)[:k]
        out = []
        for i in order:
            score = float(scores[i])
            if score <= 0:
                continue
            out.append({**self.chunks[i], "score": round(score, 4)})
        return out

    def _offline_scores(self, query: str):
        counts = Counter(_tokens(query))
        vec = [0.0] * len(self._vocab)
        for t, c in counts.items():
            idx = self._vocab.get(t)
            if idx is not None:
                vec[idx] = (1 + math.log(c)) * self._idf[idx]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vec = [v / norm for v in vec]
        if np is not None:
            return self.matrix @ np.array(vec, dtype="float32")
        return [sum(a * b for a, b in zip(row, vec)) for row in self.matrix]


# 11.5 模块级单例：整个应用共用一个索引，首次访问时构建
kb = KnowledgeBase()
