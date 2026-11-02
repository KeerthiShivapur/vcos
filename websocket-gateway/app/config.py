"""
Configuration Management for WebSocket Gateway
"""

import os
from functools import lru_cache
from typing import List, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8001
    workers: int = 4
    timeout: int = 30
    keepalive: int = 5
    max_connections: int = 10000
    max_message_size: int = 16777216


class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 1
    password: Optional[str] = None
    max_connections: int = 100
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    health_check_interval: int = 30


class PubSubSettings(BaseSettings):
    channels: "PubSubChannels" = Field(default_factory=lambda: PubSubChannels())
    publish_timeout: int = 5
    subscribe_timeout: int = 10


class PubSubChannels(BaseSettings):
    presence: str = "vcos:presence"
    crdt: str = "vcos:crdt"
    signaling: str = "vcos:signaling"
    notifications: str = "vcos:notifications"
    system: str = "vcos:system"


class WebSocketSettings(BaseSettings):
    ping_interval: int = 25
    ping_timeout: int = 20
    close_timeout: int = 10
    max_queue_size: int = 1000
    compression: bool = True
    per_message_deflate: bool = True


class AuthSettings(BaseSettings):
    jwt_secret: str = "change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry: int = 3600
    token_header: str = "Authorization"
    token_query_param: str = "token"
    allow_anonymous: bool = False


class RateLimitSettings(BaseSettings):
    enabled: bool = True
    requests_per_second: int = 100
    burst: int = 200
    redis_prefix: str = "vcos:ws:ratelimit:"


class StickySessionSettings(BaseSettings):
    enabled: bool = True
    cookie_name: str = "vcos_ws_session"
    cookie_secure: bool = True
    cookie_httponly: bool = True
    cookie_samesite: str = "lax"
    session_ttl: int = 86400


class MetricsSettings(BaseSettings):
    enabled: bool = True
    port: int = 9091
    path: str = "/metrics"


class TracingSettings(BaseSettings):
    enabled: bool = True
    service_name: str = "vcos-websocket-gateway"
    exporter: str = "prometheus"
    sampling_rate: float = 0.1


class LoggingSettings(BaseSettings):
    level: str = "INFO"
    format: str = "json"
    output: str = "stdout"
    access_log: bool = True
    error_log: bool = True


class HealthSettings(BaseSettings):
    enabled: bool = True
    path: str = "/health"
    interval: int = 30


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )
    
    server: ServerSettings = Field(default_factory=ServerSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    pubsub: PubSubSettings = Field(default_factory=PubSubSettings)
    websocket: WebSocketSettings = Field(default_factory=WebSocketSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    sticky_sessions: StickySessionSettings = Field(default_factory=StickySessionSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    tracing: TracingSettings = Field(default_factory=TracingSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    health: HealthSettings = Field(default_factory=HealthSettings)


_settings: Optional["Settings"] = None


def load_config(config_path: Optional[str] = None) -> None:
    """Load configuration from YAML file"""
    global _settings
    
    if config_path is None:
        config_path = os.getenv("CONFIG_PATH", "config.yaml")
    
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)
        _settings = Settings(**config_data)
    else:
        _settings = Settings()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    if _settings is None:
        load_config()
    return _settings


settings = get_settings()