from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://farewise:farewise@localhost:5432/farewise"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # Amadeus
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_base_url: str = "https://test.api.amadeus.com"

    # Anthropic
    anthropic_api_key: str = ""

    # OpenAI
    openai_api_key: str = ""

    # PredictHQ — Event Intelligence
    predicthq_access_token: str = ""
    predicthq_base_url: str = "https://api.predicthq.com/v1"
    event_cache_ttl_hours: int = 24
    event_min_rank: int = 40
    event_search_radius_km: int = 30

    # Price Watches
    price_watch_check_interval_hours: int = 6

    # Hotel Search
    hotel_search_cache_ttl: int = 1800

    # Analytics
    analytics_snapshot_enabled: bool = True
    leaderboard_min_trips: int = 1
    gamification_enabled: bool = True

    # Price Intelligence
    price_intelligence_enabled: bool = True

    # Scheduler
    scheduler_enabled: bool = True

    # CORS
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
