"""Google Calendar OAuth2 installed-app authentication."""

from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import GOOGLE_CLIENT_SECRETS, GOOGLE_TOKEN_PATH

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_credentials(*, open_browser: bool = True) -> Credentials:
    """Load or refresh OAuth credentials; run local browser flow if needed."""
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

    if not GOOGLE_CLIENT_SECRETS.exists():
        raise FileNotFoundError(
            f"Missing Google OAuth client secrets at {GOOGLE_CLIENT_SECRETS}. "
            "Download a Desktop OAuth client JSON from Google Cloud Console and save it there. "
            "See README.md for setup steps."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CLIENT_SECRETS), SCOPES)
    if open_browser:
        creds = flow.run_local_server(port=0)
    else:
        creds = flow.run_console()

    GOOGLE_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


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
