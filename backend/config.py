"""
Application configuration using Pydantic Settings.
All settings can be overridden via environment variables or .env file.
"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application settings — all local, no cloud."""

    # --- App ---
    app_name: str = "TA Data Analysis Agent"
    app_version: str = "0.1.0"
    debug: bool = True

    # --- Ollama / LLM ---
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    llm_temperature: float = 0.1       # Low temp for analytical accuracy
    llm_max_tokens: int = 4096
    llm_timeout: int = 120             # seconds

    # --- File Upload ---
    upload_dir: Path = Path("./data/uploads")
    max_file_size_mb: int = 100        # Max upload size
    allowed_extensions: list[str] = [".csv", ".xlsx", ".xls"]

    # --- Analysis ---
    max_dataset_rows: int = 100_000    # Safety limit
    max_dataset_size_mb: int = 10      # Per constraint: ≤10MB for <10s response

    # --- Visualization ---
    chart_default_width: int = 800
    chart_default_height: int = 500

    # --- DuckDB ---
    duckdb_memory_limit: str = "2GB"

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    # Public URL used to construct absolute chart image URLs (browser-accessible)
    # Override via TA_PUBLIC_URL env var if backend is behind a proxy or different host
    public_url: str = "http://localhost:8000"
    cors_origins: list[str] = [
        "http://localhost:3000",     # Open WebUI
        "http://localhost:5173",     # Svelte dev server
        "http://localhost:8080",
    ]

    # --- Language ---
    default_language: str = "en"  # "id" for Indonesian, "en" for English

    model_config = {
        "env_file": ".env",
        "env_prefix": "TA_",
    }


settings = Settings()
