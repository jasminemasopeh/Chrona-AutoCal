"""Local JSON preference / memory store."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import PREFERENCES_PATH, TIMEZONE

DEFAULT_PREFERENCES: dict[str, Any] = {
    "work_hours": {"start": "09:00", "end": "17:00"},
    "timezone": TIMEZONE,
    "time_of_day_biases": {
        "deep_work": "morning",
        "meetings": "afternoon",
        "personal": "evening",
        "health": "morning",
    },
    "break_habits": {
        "prefer_breaks_between_tasks": True,
        "min_break_minutes": 10,
    },
    "categories": {
        "work": {"typical_duration_minutes": 60, "preferred_color_id": None},
        "personal": {"typical_duration_minutes": 30, "preferred_color_id": None},
        "health": {"typical_duration_minutes": 45, "preferred_color_id": None},
        "errands": {"typical_duration_minutes": 30, "preferred_color_id": None},
        "other": {"typical_duration_minutes": 30, "preferred_color_id": None},
    },
    "feedback_summary": {
        "accepted_patterns": [],
        "rejected_patterns": [],
        "notes": [],
    },
    "feedback_log": [],
}


def _ensure_file(path: Path = PREFERENCES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_PREFERENCES, indent=2) + "\n", encoding="utf-8")


def load_preferences(path: Path = PREFERENCES_PATH) -> dict[str, Any]:
    _ensure_file(path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    # Fill any missing top-level keys from defaults
    merged = deepcopy(DEFAULT_PREFERENCES)
    merged.update(data)
    return merged


def save_preferences(prefs: dict[str, Any], path: Path = PREFERENCES_PATH) -> dict[str, Any]:
    _ensure_file(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)
        f.write("\n")
    return prefs


def get_preferences() -> dict[str, Any]:
    return load_preferences()


def update_preferences(updates: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge top-level keys; deep-merge known nested dicts."""
    prefs = load_preferences()
    for key, value in updates.items():
        if (
            key in prefs
            and isinstance(prefs[key], dict)
            and isinstance(value, dict)
            and key != "feedback_log"
        ):
            prefs[key] = {**prefs[key], **value}
        else:
            prefs[key] = value
    return save_preferences(prefs)


def set_category_color(category: str, color_id: str) -> dict[str, Any]:
    prefs = load_preferences()
    categories = prefs.setdefault("categories", {})
    cat = categories.setdefault(category, {"typical_duration_minutes": 30, "preferred_color_id": None})
    cat["preferred_color_id"] = str(color_id)
    return save_preferences(prefs)


def record_feedback(
    action: str,
    task_title: str,
    *,
    proposed_start: str | None = None,
    proposed_end: str | None = None,
    final_start: str | None = None,
    final_end: str | None = None,
    category: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Record accept / reject / edit feedback and update summary patterns."""
    prefs = load_preferences()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "task_title": task_title,
        "category": category,
        "proposed_start": proposed_start,
        "proposed_end": proposed_end,
        "final_start": final_start,
        "final_end": final_end,
        "reason": reason,
    }
    prefs.setdefault("feedback_log", []).append(entry)

    summary = prefs.setdefault(
        "feedback_summary",
        {"accepted_patterns": [], "rejected_patterns": [], "notes": []},
    )

    hour_hint = None
    for ts in (final_start, proposed_start):
        if ts and "T" in ts:
            try:
                hour = int(ts.split("T")[1][:2])
                if hour < 12:
                    hour_hint = "morning"
                elif hour < 17:
                    hour_hint = "afternoon"
                else:
                    hour_hint = "evening"
                break
            except (ValueError, IndexError):
                pass

    pattern = {
        "task_title": task_title,
        "category": category,
        "time_of_day": hour_hint,
        "action": action,
    }

    if action == "accept":
        summary.setdefault("accepted_patterns", []).append(pattern)
        if category and hour_hint:
            biases = prefs.setdefault("time_of_day_biases", {})
            biases[category] = hour_hint
    elif action == "reject":
        summary.setdefault("rejected_patterns", []).append(pattern)
        if reason:
            summary.setdefault("notes", []).append(f"Rejected '{task_title}': {reason}")
    elif action == "edit":
        summary.setdefault("notes", []).append(
            f"Edited '{task_title}' from {proposed_start} to {final_start}"
        )
        if category and hour_hint:
            biases = prefs.setdefault("time_of_day_biases", {})
            biases[category] = hour_hint

    # Keep logs bounded for a course demo
    prefs["feedback_log"] = prefs["feedback_log"][-200:]
    for key in ("accepted_patterns", "rejected_patterns", "notes"):
        if key in summary and isinstance(summary[key], list):
            summary[key] = summary[key][-50:]

    return save_preferences(prefs)
