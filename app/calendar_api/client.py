"""Google Calendar read/write helpers used as agent tools."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, time
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from app.calendar_api.auth import get_calendar_service
from app.config import GOOGLE_CALENDAR_ID, TIMEZONE
from app.memory.store import get_preferences


def _tz() -> ZoneInfo:
    prefs = get_preferences()
    return ZoneInfo(prefs.get("timezone") or TIMEZONE)


def _parse_day(day: str) -> date:
    """Parse YYYY-MM-DD into a date."""
    return date.fromisoformat(day[:10])


def _day_bounds(day: str) -> tuple[datetime, datetime]:
    d = _parse_day(day)
    tz = _tz()
    start = datetime.combine(d, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _friendly_http_error(exc: HttpError) -> str:
    """Prefer Google's JSON error message when present."""
    try:
        content = exc.content.decode("utf-8") if isinstance(exc.content, (bytes, bytearray)) else str(exc.content)
        parsed = json.loads(content)
        message = (parsed.get("error") or {}).get("message")
        if message:
            return message
    except Exception:  # noqa: BLE001
        pass
    return str(exc)


def get_events(
    day: str | None = None,
    start: str | None = None,
    end: str | None = None,
    *,
    calendar_id: str | None = None,
    all_calendars: bool = False,
) -> dict[str, Any]:
    """List events for a day or explicit ISO start/end range."""
    service = get_calendar_service()
    tz = _tz()

    if start and end:
        time_min = datetime.fromisoformat(start).astimezone(tz)
        time_max = datetime.fromisoformat(end).astimezone(tz)
    elif day:
        time_min, time_max = _day_bounds(day)
    else:
        today = datetime.now(tz).date().isoformat()
        time_min, time_max = _day_bounds(today)

    calendar_ids: list[str]
    if all_calendars:
        listed = list_calendars()
        if not listed.get("ok"):
            return listed
        calendar_ids = [c["id"] for c in listed.get("calendars", []) if c.get("id")]
    else:
        calendar_ids = [calendar_id or GOOGLE_CALENDAR_ID]

    events: list[dict[str, Any]] = []
    try:
        for cal_id in calendar_ids:
            result = (
                service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=_iso(time_min),
                    timeMax=_iso(time_max),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            for item in result.get("items", []):
                start_raw = item.get("start", {})
                end_raw = item.get("end", {})
                events.append(
                    {
                        "id": item.get("id"),
                        "calendar_id": cal_id,
                        "summary": item.get("summary", "(no title)"),
                        "start": start_raw.get("dateTime") or start_raw.get("date"),
                        "end": end_raw.get("dateTime") or end_raw.get("date"),
                        "colorId": item.get("colorId"),
                        "description": item.get("description"),
                    }
                )
    except HttpError as exc:
        return {"ok": False, "error": _friendly_http_error(exc)}

    events.sort(key=lambda e: e.get("start") or "")
    return {
        "ok": True,
        "time_min": _iso(time_min),
        "time_max": _iso(time_max),
        "events": events,
        "count": len(events),
        "calendar_ids": calendar_ids,
    }


def list_calendars() -> dict[str, Any]:
    """List calendars in the user's calendar list (personal, work, school, …)."""
    service = get_calendar_service()
    try:
        result = service.calendarList().list().execute()
    except HttpError as exc:
        return {"ok": False, "error": _friendly_http_error(exc)}

    calendars = []
    for item in result.get("items", []):
        calendars.append(
            {
                "id": item.get("id"),
                "summary": item.get("summary") or item.get("id"),
                "primary": bool(item.get("primary")),
                "access_role": item.get("accessRole"),
                "backgroundColor": item.get("backgroundColor"),
                "foregroundColor": item.get("foregroundColor"),
                "colorId": item.get("colorId"),
                "selected": item.get("selected", True),
            }
        )
    calendars.sort(key=lambda c: (not c["primary"], (c["summary"] or "").lower()))
    return {"ok": True, "calendars": calendars, "count": len(calendars)}


def update_calendar_appearance(
    calendar_id: str,
    *,
    background_color: str | None = None,
    foreground_color: str | None = None,
    color_id: str | None = None,
) -> dict[str, Any]:
    """
    Update a calendar's list color (applies to the whole calendar, including mobile).

    Prefer background/foreground hex when custom colors are requested.
    """
    service = get_calendar_service()
    body: dict[str, Any] = {}
    use_rgb = False
    if background_color:
        body["backgroundColor"] = background_color if background_color.startswith("#") else f"#{background_color}"
        use_rgb = True
    if foreground_color:
        body["foregroundColor"] = foreground_color if foreground_color.startswith("#") else f"#{foreground_color}"
        use_rgb = True
    if color_id and not use_rgb:
        body["colorId"] = str(color_id)
    if not body:
        return {"ok": False, "error": "Provide background_color/foreground_color or color_id"}

    try:
        updated = (
            service.calendarList()
            .patch(calendarId=calendar_id, colorRgbFormat=use_rgb, body=body)
            .execute()
        )
    except HttpError as exc:
        return {"ok": False, "error": _friendly_http_error(exc)}

    return {
        "ok": True,
        "calendar": {
            "id": updated.get("id"),
            "summary": updated.get("summary"),
            "backgroundColor": updated.get("backgroundColor"),
            "foregroundColor": updated.get("foregroundColor"),
            "colorId": updated.get("colorId"),
        },
    }


def _work_window(day: str) -> tuple[datetime, datetime]:
    prefs = get_preferences()
    work = prefs.get("work_hours", {"start": "09:00", "end": "17:00"})
    d = _parse_day(day)
    tz = _tz()
    start_h, start_m = map(int, work.get("start", "09:00").split(":"))
    end_h, end_m = map(int, work.get("end", "17:00").split(":"))
    start_dt = datetime.combine(d, time(start_h, start_m), tzinfo=tz)
    end_dt = datetime.combine(d, time(end_h, end_m), tzinfo=tz)
    return start_dt, end_dt


def _busy_intervals(day: str) -> list[tuple[datetime, datetime]]:
    listed = get_events(day=day, all_calendars=True)
    if not listed.get("ok"):
        return []

    tz = _tz()
    busy: list[tuple[datetime, datetime]] = []
    for ev in listed.get("events", []):
        start_s = ev.get("start")
        end_s = ev.get("end")
        if not start_s or not end_s:
            continue
        # Date-only all-day events (holidays, pay days, etc.) should not block
        # timed scheduling — Google Calendar still allows timed events that day.
        if "T" not in str(start_s):
            continue
        start_dt = datetime.fromisoformat(start_s).astimezone(tz)
        end_dt = datetime.fromisoformat(end_s).astimezone(tz)
        busy.append((start_dt, end_dt))

    busy.sort(key=lambda x: x[0])
    # Merge overlaps
    merged: list[tuple[datetime, datetime]] = []
    for interval in busy:
        if not merged or interval[0] > merged[-1][1]:
            merged.append(interval)
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], interval[1]))
    return merged


def find_free_slots(
    day: str,
    duration_minutes: int = 30,
    *,
    earliest: str | None = None,
    latest: str | None = None,
) -> dict[str, Any]:
    """Find free windows of at least duration_minutes within work hours (or custom bounds)."""
    prefs = get_preferences()
    work_start, work_end = _work_window(day)
    tz = _tz()

    window_start = work_start
    window_end = work_end
    if earliest:
        window_start = max(window_start, datetime.fromisoformat(earliest).astimezone(tz))
    if latest:
        window_end = min(window_end, datetime.fromisoformat(latest).astimezone(tz))

    if window_end <= window_start:
        return {"ok": True, "day": day, "duration_minutes": duration_minutes, "free_slots": []}

    busy = _busy_intervals(day)
    duration = timedelta(minutes=int(duration_minutes))
    cursor = window_start
    free_slots: list[dict[str, str]] = []

    for busy_start, busy_end in busy:
        if busy_end <= cursor:
            continue
        if busy_start > cursor:
            gap_end = min(busy_start, window_end)
            if gap_end - cursor >= duration:
                free_slots.append({"start": _iso(cursor), "end": _iso(gap_end)})
        cursor = max(cursor, busy_end)
        if cursor >= window_end:
            break

    if cursor < window_end and window_end - cursor >= duration:
        free_slots.append({"start": _iso(cursor), "end": _iso(window_end)})

    # Also return concrete candidate starts (step 15 min) for agent convenience
    candidates: list[dict[str, str]] = []
    step = timedelta(minutes=15)
    for slot in free_slots:
        s = datetime.fromisoformat(slot["start"])
        e = datetime.fromisoformat(slot["end"])
        t = s
        while t + duration <= e:
            candidates.append({"start": _iso(t), "end": _iso(t + duration)})
            t += step

    return {
        "ok": True,
        "day": day,
        "duration_minutes": duration_minutes,
        "work_hours": prefs.get("work_hours"),
        "free_windows": free_slots,
        "candidate_slots": candidates[:40],
    }


def create_event(
    summary: str,
    start: str,
    end: str,
    *,
    description: str | None = None,
    color_id: str | None = None,
    calendar_id: str | None = None,
    check_conflicts: bool = True,
) -> dict[str, Any]:
    """Create a calendar event on the chosen calendar; refuse on conflicts."""
    service = get_calendar_service()
    tz = _tz()
    target_calendar = calendar_id or GOOGLE_CALENDAR_ID
    start_dt = datetime.fromisoformat(start).astimezone(tz)
    end_dt = datetime.fromisoformat(end).astimezone(tz)

    if end_dt <= start_dt:
        return {"ok": False, "error": "end must be after start"}

    if check_conflicts:
        day = start_dt.date().isoformat()
        existing = get_events(day=day, all_calendars=True)
        if existing.get("ok"):
            for ev in existing.get("events", []):
                ev_start_s = ev.get("start")
                ev_end_s = ev.get("end")
                if not ev_start_s or not ev_end_s or "T" not in str(ev_start_s):
                    continue
                ev_start = datetime.fromisoformat(ev_start_s).astimezone(tz)
                ev_end = datetime.fromisoformat(ev_end_s).astimezone(tz)
                if start_dt < ev_end and end_dt > ev_start:
                    return {
                        "ok": False,
                        "error": "conflict",
                        "conflict_with": ev,
                        "message": (
                            f"Proposed slot conflicts with '{ev.get('summary')}' "
                            f"({ev_start_s} – {ev_end_s}). Replan to a free slot."
                        ),
                    }

    body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": _iso(start_dt), "timeZone": str(tz)},
        "end": {"dateTime": _iso(end_dt), "timeZone": str(tz)},
    }
    if description:
        body["description"] = description
    if color_id:
        body["colorId"] = str(color_id)

    try:
        created = (
            service.events()
            .insert(calendarId=target_calendar, body=body)
            .execute()
        )
    except HttpError as exc:
        return {"ok": False, "error": _friendly_http_error(exc)}

    return {
        "ok": True,
        "event": {
            "id": created.get("id"),
            "calendar_id": target_calendar,
            "summary": created.get("summary"),
            "start": created.get("start", {}).get("dateTime"),
            "end": created.get("end", {}).get("dateTime"),
            "htmlLink": created.get("htmlLink"),
            "colorId": created.get("colorId"),
        },
    }


def update_event_color(
    event_id: str,
    color_id: str,
    *,
    calendar_id: str | None = None,
) -> dict[str, Any]:
    """Set a Google Calendar event colorId (1–11)."""
    service = get_calendar_service()
    target_calendar = calendar_id or GOOGLE_CALENDAR_ID
    try:
        updated = (
            service.events()
            .patch(
                calendarId=target_calendar,
                eventId=event_id,
                body={"colorId": str(color_id)},
            )
            .execute()
        )
    except HttpError as exc:
        return {"ok": False, "error": _friendly_http_error(exc)}

    return {
        "ok": True,
        "event": {
            "id": updated.get("id"),
            "calendar_id": target_calendar,
            "summary": updated.get("summary"),
            "colorId": updated.get("colorId"),
        },
    }


def delete_event(event_id: str, *, calendar_id: str | None = None) -> dict[str, Any]:
    """Delete an event by id (and calendar id when known)."""
    service = get_calendar_service()
    candidates = [calendar_id] if calendar_id else []
    if not candidates:
        listed = list_calendars()
        if listed.get("ok"):
            candidates = [c["id"] for c in listed.get("calendars", []) if c.get("id")]
        if not candidates:
            candidates = [GOOGLE_CALENDAR_ID]

    last_error = None
    for cal_id in candidates:
        try:
            service.events().delete(calendarId=cal_id, eventId=event_id).execute()
            return {"ok": True, "deleted": event_id, "calendar_id": cal_id}
        except HttpError as exc:
            last_error = _friendly_http_error(exc)
            continue
    return {"ok": False, "error": last_error or "Event not found"}


def update_event_times(
    event_id: str,
    start: str,
    end: str,
    *,
    calendar_id: str | None = None,
) -> dict[str, Any]:
    """Move an event to a new start/end."""
    service = get_calendar_service()
    tz = _tz()
    target_calendar = calendar_id or GOOGLE_CALENDAR_ID
    start_dt = datetime.fromisoformat(start).astimezone(tz)
    end_dt = datetime.fromisoformat(end).astimezone(tz)
    try:
        updated = (
            service.events()
            .patch(
                calendarId=target_calendar,
                eventId=event_id,
                body={
                    "start": {"dateTime": _iso(start_dt), "timeZone": str(tz)},
                    "end": {"dateTime": _iso(end_dt), "timeZone": str(tz)},
                },
            )
            .execute()
        )
    except HttpError as exc:
        return {"ok": False, "error": _friendly_http_error(exc)}
    return {
        "ok": True,
        "event": {
            "id": updated.get("id"),
            "calendar_id": target_calendar,
            "summary": updated.get("summary"),
            "start": updated.get("start", {}).get("dateTime"),
            "end": updated.get("end", {}).get("dateTime"),
            "colorId": updated.get("colorId"),
        },
    }
