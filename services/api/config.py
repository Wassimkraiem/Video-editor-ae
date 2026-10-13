from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./video-editor.db"
    storage_root: str = "/tmp/video-editor-storage"
    projects_root: str = "/tmp/video-editor-projects"
    web_origin: str = "http://localhost:3000"
    access_token_secret: str = "development-secret-change-me-use-a-32-byte-secret"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 2_592_000
    max_upload_bytes: int = 1_073_741_824
    anthropic_api_key: str = ""
    # Alternative to an API key: a subscription token from `claude setup-token`.
    claude_code_oauth_token: str = ""
    agent_model: str = "claude-opus-5-5"
    image_model: str = "gpt-image-1"
    style_extraction_enabled: bool = False
    # Run jobs inside the API process when no Postgres queue is configured.
    local_worker_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
