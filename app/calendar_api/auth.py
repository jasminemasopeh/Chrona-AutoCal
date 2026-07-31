"""Google Calendar OAuth2 web-application authentication."""

from __future__ import annotations

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.config import GOOGLE_CLIENT_SECRETS, GOOGLE_REDIRECT_URI, GOOGLE_TOKEN_PATH

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class AuthRequiredError(RuntimeError):
    """Raised when Calendar API is called without a saved OAuth token."""


def _ensure_client_secrets() -> None:
    if not GOOGLE_CLIENT_SECRETS.exists():
        raise FileNotFoundError(
            f"Missing Google OAuth client secrets at {GOOGLE_CLIENT_SECRETS}. "
            "Download a Web OAuth client JSON from Google Cloud Console and save it there. "
            "See README.md for setup steps."
        )


def build_oauth_flow() -> Flow:
    """Build an OAuth Flow configured for the web redirect URI."""
    _ensure_client_secrets()
    # Allow http://127.0.0.1 for local development.
    if GOOGLE_REDIRECT_URI.startswith("http://"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    # Google may return extra granted scopes; don't fail the token exchange.
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    return Flow.from_client_secrets_file(
        str(GOOGLE_CLIENT_SECRETS),
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )


def authorization_url() -> tuple[str, str]:
    """Return (Google auth URL, state) for the Connect Google redirect."""
    flow = build_oauth_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, state


def exchange_code(code: str) -> Credentials:
    """Exchange an authorization code for credentials and persist token.json."""
    flow = build_oauth_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    GOOGLE_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_credentials(*, open_browser: bool = True) -> Credentials:
    """Load or refresh OAuth credentials from token.json.

    Interactive browser login is handled by the /api/auth/google redirect routes.
    open_browser is kept for call-site compatibility and ignored.
    """
    del open_browser  # web redirect flow only
    creds: Credentials | None = None

    if GOOGLE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        GOOGLE_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        return creds

    _ensure_client_secrets()
    raise AuthRequiredError(
        "Google Calendar is not connected. Click Connect Google to authorize."
    )


def get_calendar_service(*, open_browser: bool = True):
    """Return an authenticated Google Calendar API service client."""
    creds = get_credentials(open_browser=open_browser)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def is_authenticated() -> bool:
    """True if a usable token already exists (may still need refresh)."""
    if not GOOGLE_TOKEN_PATH.exists():
        return False
    try:
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), SCOPES)
        return bool(creds and (creds.valid or creds.refresh_token))
    except Exception:
        return False
