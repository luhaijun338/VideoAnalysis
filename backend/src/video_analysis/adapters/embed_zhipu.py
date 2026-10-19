from __future__ import annotations

from video_analysis.config import settings


class ZhipuEmbedAdapter:
    """Remote text embeddings via OpenAI-compatible API."""

    @property
    def model_name(self) -> str:
        return settings.embed_model

    def embed(self, text: str) -> list[float]:
        from openai import OpenAI

        key = settings.embed_api_key or settings.zhipu_api_key
        if not key:
            raise RuntimeError("embed_api_key not configured")

        client = OpenAI(
            api_key=key,
            base_url=settings.embed_base_url,
        )
        resp = client.embeddings.create(
            model=settings.embed_model,
            input=text,
            dimensions=settings.embed_dimensions,
        )
        return [float(x) for x in resp.data[0].embedding]
