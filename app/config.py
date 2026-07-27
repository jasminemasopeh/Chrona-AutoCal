"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# Prefer OpenRouter; fall back to OPENAI_API_KEY for convenience.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# OpenRouter model ids look like "openai/gpt-4o-mini"
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini"),
)
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://127.0.0.1:8000")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Chrona Calendar Agent")

# Back-compat aliases used by older docs / imports
OPENAI_API_KEY = OPENROUTER_API_KEY
OPENAI_MODEL = OPENROUTER_MODEL

TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

GOOGLE_CLIENT_SECRETS = Path(
    os.getenv("GOOGLE_CLIENT_SECRETS", str(ROOT_DIR / "credentials" / "client_secret.json"))
)
GOOGLE_TOKEN_PATH = Path(
    os.getenv("GOOGLE_TOKEN_PATH", str(ROOT_DIR / "credentials" / "token.json"))
)
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

PREFERENCES_PATH = ROOT_DIR / "data" / "preferences.json"
UPLOADS_DIR = ROOT_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
