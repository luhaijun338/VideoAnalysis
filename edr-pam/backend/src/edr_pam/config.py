from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://va:va@localhost:5432/edr_pam"
    api_host: str = "127.0.0.1"
    api_port: int = 8001


settings = Settings()
