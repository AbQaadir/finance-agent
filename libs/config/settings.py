"""
Enterprise configuration management for Salon Payments Ops.
Leverages Pydantic Settings for strictly typed, environment-driven configuration.
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    # Application & Environment
    app_name: str = "Salon Payments Ops Agent"
    environment: str = Field(default="development", description="development, staging, or production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # Database Configuration (PostgreSQL in production, SQLite for local)
    database_url: str = Field(
        default="sqlite:///./salon_payments.db",
        description="SQLAlchemy database connection string",
    )
    db_pool_size: int = Field(default=10, description="Database pool size for PostgreSQL")
    db_max_overflow: int = Field(default=20, description="Database max overflow connections")

    # Stripe Configuration
    stripe_api_key: str = Field(
        default="sk_test_synthetic_salon_key",
        description="Stripe secret API key",
    )
    stripe_webhook_secret: str = Field(
        default="whsec_mock",
        description="Stripe webhook signing secret",
    )
    stripe_live_mode: bool = Field(
        default=False,
        description="When true, operates in live Stripe environment",
    )

    # API Security & Authentication
    payments_api_key: Optional[str] = Field(
        default=None,
        description="Optional API key requirement for client payments requests",
    )
    approval_api_key: Optional[str] = Field(
        default=None,
        description="API key required for approving financial proposals",
    )

    # Google Gemini & ADK Configuration
    google_api_key: Optional[str] = Field(default=None)
    google_model: str = Field(default="gemini-3.8-flash")
    google_genai_use_vertexai: bool = Field(default=False)
    vertexai_project: Optional[str] = Field(default=None)
    vertexai_location: Optional[str] = Field(default="us-central1")

    # Operational Thresholds
    max_proposal_amount_minor: int = Field(
        default=100000,
        description="Maximum financial proposal ceiling in minor units ($1,000.00)",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


settings = AppSettings()
