"""Vector embedding service backed by local Ollama."""

from typing import List

import httpx
from langchain_core.embeddings import Embeddings
from loguru import logger

from app.config import config


class OllamaEmbeddings(Embeddings):
    """LangChain Embeddings adapter for Ollama local models."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "nomic-embed-text:latest"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        logger.info(f"Ollama Embeddings initialized: model={model}, base_url={self.base_url}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        try:
            logger.info(f"Embedding {len(texts)} document chunks with Ollama")
            embeddings = self._embed_many(texts)
            if embeddings:
                logger.debug(f"Ollama embedding dimension: {len(embeddings[0])}")
            return embeddings
        except Exception as e:
            logger.error(f"Ollama document embedding failed: {e}")
            raise RuntimeError(f"Ollama document embedding failed: {e}") from e

    def embed_query(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Query text cannot be empty")
        try:
            return self._embed_many([text])[0]
        except Exception as e:
            logger.error(f"Ollama query embedding failed: {e}")
            raise RuntimeError(f"Ollama query embedding failed: {e}") from e

    def _embed_many(self, texts: List[str]) -> List[List[float]]:
        payload = {"model": self.model, "input": texts}
        try:
            response = httpx.post(f"{self.base_url}/api/embed", json=payload, timeout=120.0)
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings")
            if embeddings:
                return embeddings
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise
        except (KeyError, ValueError):
            raise

        # Older Ollama versions expose only /api/embeddings
        embeddings = []
        for text in texts:
            response = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=120.0,
            )
            response.raise_for_status()
            embedding = response.json().get("embedding")
            if not embedding:
                raise RuntimeError("Ollama returned no embedding")
            embeddings.append(embedding)
        return embeddings


vector_embedding_service = OllamaEmbeddings(
    base_url=config.ollama_base_url,
    model=config.ollama_embedding_model,
)
