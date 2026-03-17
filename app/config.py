from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./migration.db"
    EXPORT_DIR: str = "./exports"
    MAX_CONCURRENT_REQUESTS: int = 5
    CRAWL_DELAY: float = 1.0
    USER_AGENT: str = (
        "MigrationToolkit/1.0 "
        "(+https://github.com/shopify-migration-toolkit; "
        "compatible; crawl-bot)"
    )

    model_config = {"env_prefix": "MT_", "env_file": ".env"}


settings = Settings()
