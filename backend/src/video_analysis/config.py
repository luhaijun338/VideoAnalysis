from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://va:va@localhost:5432/video_analysis"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: Path = Path("./data/videos")
    zhipu_api_key: str = "sk-8NLV6VlH5HlxVxPGlO1y1ssx3wQk9wth"
    caption_model: str = "qwen3.5-flash"
    caption_base_url: str = "https://aigw.telecomjs.com/v1"
    embed_api_key: str = "sk-8NLV6VlH5HlxVxPGlO1y1ssx3wQk9wth"
    embed_base_url: str = "https://aigw.telecomjs.com/v1"
    embed_model: str = "text-embedding-v4"
    embed_dimensions: int = 1024
    max_upload_bytes: int = 4 * 1024 * 1024 * 1024
    allowed_suffixes: tuple[str, ...] = (".mp4", ".webm", ".mov")


settings = Settings()
