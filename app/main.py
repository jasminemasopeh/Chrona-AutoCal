"""FastAPI entrypoint for the Calendar Scheduling Agent."""

from __future__ import annotations

import shutil
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.agent.loop import run_palette_agent, run_scheduling_agent
from app.calendar_api import client as calendar_client
from app.calendar_api.auth import authorization_url, exchange_code, is_authenticated
from app.config import UPLOADS_DIR
from app.memory import store as memory_store
from app.palette.extract import extract_palette_from_image
from app.tasks import filter_tasks_already_scheduled

WEB_DIR = Path(__file__).resolve().parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

app = FastAPI(title="Calendar Scheduling Agent", version="1.1.0")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


class FeedbackItem(BaseModel):
    action: str = Field(..., pattern="^(accept|reject|edit)$")
    task_title: str
    category: str | None = None
    proposed_start: str | None = None
    proposed_end: str | None = None
    final_start: str | None = None
    final_end: str | None = None
    event_id: str | None = None
    calendar_id: str | None = None
    reason: str | None = None


class FeedbackRequest(BaseModel):
    items: list[FeedbackItem]


class DeleteEventRequest(BaseModel):
    event_id: str
    calendar_id: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "today": date.today().isoformat(),
            "authenticated": is_authenticated(),
        },
    )


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "google_authenticated": is_authenticated(),
        "preferences_loaded": True,
    }


@app.get("/api/auth/google")
async def auth_google_start() -> RedirectResponse:
    """Redirect the browser to Google's OAuth consent screen."""
    try:
        url, state = authorization_url()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    response = RedirectResponse(url)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        max_age=600,
        samesite="lax",
    )
    return response


@app.get("/api/auth/google/callback")
async def auth_google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle Google's redirect, exchange the code, and return to the UI."""
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    expected_state = request.cookies.get("oauth_state")
    if not expected_state or not state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    try:
        exchange_code(code)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("oauth_state")
    return response


@app.get("/api/preferences")
async def api_get_preferences() -> dict[str, Any]:
    return {"ok": True, "preferences": memory_store.get_preferences()}


@app.get("/api/calendars")
async def api_calendars() -> dict[str, Any]:
    try:
        return calendar_client.list_calendars()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@app.post("/api/plan")
async def plan_schedule(
    task_list: str = Form(...),
    target_day: str = Form(...),
    write_to_calendar: str = Form("true"),
) -> JSONResponse:
    if not task_list.strip():
        raise HTTPException(status_code=400, detail="task_list is required")

    filtered = filter_tasks_already_scheduled(task_list, target_day)
    skipped = filtered.get("skipped_tasks") or []
    kept_list = filtered.get("filtered_task_list") or ""

    if not (filtered.get("kept_tasks") or []):
        summary = (
            "Every task already exists as an event on that day, so nothing new was scheduled."
            if skipped
            else "No tasks to schedule."
        )
        return JSONResponse(
            {
                "ok": True,
                "summary": summary,
                "proposals": [],
                "skipped_tasks": skipped,
                "tool_trace": [],
            }
        )

    try:
        result = run_scheduling_agent(
            task_list=kept_list,
            target_day=target_day,
            write_to_calendar=_as_bool(write_to_calendar),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    result["skipped_tasks"] = skipped
    if skipped:
        skip_note = (
            "Skipped tasks already on the calendar that day: "
            + ", ".join(skipped)
            + "."
        )
        summary = (result.get("summary") or "").strip()
        result["summary"] = f"{summary} {skip_note}".strip() if summary else skip_note

    return JSONResponse(result)


@app.post("/api/palette")
async def apply_palette(
    aesthetic_description: str = Form(""),
    style_preferences: str = Form(""),
    apply_changes: str = Form("true"),
    image: UploadFile | None = File(None),
) -> JSONResponse:
    # All inputs are optional: with none provided, a random shaded aesthetic is generated.
    image_palette = None
    saved_image: str | None = None
    if image and image.filename:
        suffix = Path(image.filename).suffix.lower() or ".png"
        dest = UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"
        with dest.open("wb") as out:
            shutil.copyfileobj(image.file, out)
        saved_image = str(dest)
        try:
            image_palette = extract_palette_from_image(dest, num_colors=6)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Palette extraction failed: {exc}") from exc

    try:
        result = run_palette_agent(
            aesthetic_description=aesthetic_description.strip() or None,
            style_preferences=style_preferences.strip() or None,
            image_palette=image_palette,
            apply_changes=_as_bool(apply_changes),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Palette agent error: {exc}") from exc

    # Remember style notes for later
    if style_preferences.strip():
        prefs = memory_store.get_preferences()
        notes = prefs.setdefault("feedback_summary", {}).setdefault("notes", [])
        notes.append(f"Palette prefs: {style_preferences.strip()}")
        memory_store.save_preferences(prefs)

    result["saved_image"] = saved_image
    return JSONResponse(result)


@app.post("/api/feedback")
async def submit_feedback(body: FeedbackRequest) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item in body.items:
        calendar_result: dict[str, Any] | None = None
        if item.action == "reject" and item.event_id:
            calendar_result = calendar_client.delete_event(
                item.event_id, calendar_id=item.calendar_id
            )
        elif item.action == "edit" and item.event_id and item.final_start and item.final_end:
            calendar_result = calendar_client.update_event_times(
                item.event_id,
                item.final_start,
                item.final_end,
                calendar_id=item.calendar_id,
            )
        elif item.action == "accept":
            calendar_result = {"ok": True, "kept": item.event_id}

        memory_store.record_feedback(
            item.action,
            item.task_title,
            proposed_start=item.proposed_start,
            proposed_end=item.proposed_end,
            final_start=item.final_start or item.proposed_start,
            final_end=item.final_end or item.proposed_end,
            category=item.category,
            reason=item.reason,
        )
        results.append(
            {
                "task_title": item.task_title,
                "action": item.action,
                "calendar": calendar_result,
            }
        )

    return {
        "ok": True,
        "results": results,
        "preferences": memory_store.get_preferences(),
    }


@app.delete("/api/events/{event_id}")
async def api_delete_event(event_id: str, calendar_id: str | None = None) -> dict[str, Any]:
    try:
        result = calendar_client.delete_event(event_id, calendar_id=calendar_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Delete failed")
    return result


@app.post("/api/events/delete")
async def api_delete_event_post(body: DeleteEventRequest) -> dict[str, Any]:
    """POST fallback for clients that prefer JSON bodies for deletes."""
    try:
        result = calendar_client.delete_event(body.event_id, calendar_id=body.calendar_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Delete failed")
    return result


@app.get("/api/events")
async def api_events(day: str) -> dict[str, Any]:
    try:
        return calendar_client.get_events(day=day, all_calendars=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
