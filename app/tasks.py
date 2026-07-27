"""Helpers for parsing and filtering the scheduling task list."""

from __future__ import annotations

import re
from typing import Any

from app.calendar_api import client as calendar_client

_BULLET_RE = re.compile(r"^[-•*]\s*")


def parse_task_lines(task_list: str) -> list[str]:
    """Split a multiline task list into cleaned task titles."""
    tasks: list[str] = []
    for line in task_list.splitlines():
        cleaned = _BULLET_RE.sub("", line.strip())
        if cleaned:
            tasks.append(cleaned)
    return tasks


def filter_tasks_already_scheduled(task_list: str, target_day: str) -> dict[str, Any]:
    """
    Drop tasks whose title exactly matches an existing event summary on target_day.

    Matching is case-insensitive after trimming whitespace.
    """
    tasks = parse_task_lines(task_list)
    existing_names: set[str] = set()
    events_result: dict[str, Any] = {"ok": True, "events": []}

    try:
        events_result = calendar_client.get_events(day=target_day, all_calendars=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "kept_tasks": tasks,
            "skipped_tasks": [],
            "filtered_task_list": task_list,
            "events_checked": False,
        }

    if events_result.get("ok"):
        for ev in events_result.get("events") or []:
            name = (ev.get("summary") or "").strip().lower()
            if name:
                existing_names.add(name)

    kept: list[str] = []
    skipped: list[str] = []
    for task in tasks:
        if task.strip().lower() in existing_names:
            skipped.append(task)
        else:
            kept.append(task)

    return {
        "ok": True,
        "kept_tasks": kept,
        "skipped_tasks": skipped,
        "filtered_task_list": "\n".join(f"- {t}" for t in kept),
        "events_checked": True,
        "existing_event_count": len(events_result.get("events") or []),
    }
