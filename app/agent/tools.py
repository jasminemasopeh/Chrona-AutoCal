"""OpenAI tool schemas and local dispatch for scheduling and palette agents."""

from __future__ import annotations

import json
from typing import Any, Callable

from app.calendar_api import client as calendar_client
from app.memory import store as memory_store

SCHEDULE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_preferences",
            "description": "Load the user's remembered scheduling preferences and feedback summary.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": "Merge updates into the local preference store (work hours, biases, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "object",
                        "description": "Partial preference object to merge.",
                    }
                },
                "required": ["updates"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_calendars",
            "description": "List the user's Google calendars (Personal, Work, School, etc.).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_events",
            "description": "List existing events for a day across all calendars (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Target day in YYYY-MM-DD format.",
                    }
                },
                "required": ["day"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_free_slots",
            "description": "Find free time windows and candidate slots for a given duration on a day.",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {"type": "string", "description": "YYYY-MM-DD"},
                    "duration_minutes": {"type": "integer", "minimum": 5},
                    "earliest": {
                        "type": "string",
                        "description": "Optional ISO datetime lower bound",
                    },
                    "latest": {
                        "type": "string",
                        "description": "Optional ISO datetime upper bound",
                    },
                },
                "required": ["day", "duration_minutes"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": (
                "Create an event on a specific Google calendar. Returns ok=false with conflict "
                "details if the slot overlaps an existing event so you can replan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start": {"type": "string", "description": "ISO-8601 start datetime"},
                    "end": {"type": "string", "description": "ISO-8601 end datetime"},
                    "calendar_id": {
                        "type": "string",
                        "description": "Target calendar id from list_calendars",
                    },
                    "description": {"type": "string"},
                },
                "required": ["summary", "start", "end", "calendar_id"],
                "additionalProperties": False,
            },
        },
    },
]

PALETTE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_calendars",
            "description": "List the user's Google calendars and their current colors.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_calendar_appearance",
            "description": (
                "Update a calendar's background/foreground colors in Google Calendar "
                "(syncs to web and mobile). Prefer hex colors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string"},
                    "background_color": {
                        "type": "string",
                        "description": "Hex background e.g. #2f5d50",
                    },
                    "foreground_color": {
                        "type": "string",
                        "description": "Hex text color e.g. #000000",
                    },
                },
                "required": ["calendar_id", "background_color"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_preferences",
            "description": "Load remembered preferences including prior palette notes.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": "Save palette-related preference notes for future runs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {"type": "object"},
                },
                "required": ["updates"],
                "additionalProperties": False,
            },
        },
    },
]

# Back-compat alias
TOOL_DEFINITIONS = SCHEDULE_TOOL_DEFINITIONS


def _tool_get_preferences(_: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "preferences": memory_store.get_preferences()}


def _tool_update_preferences(args: dict[str, Any]) -> dict[str, Any]:
    updates = args.get("updates") or {}
    prefs = memory_store.update_preferences(updates)
    return {"ok": True, "preferences": prefs}


def _tool_list_calendars(_: dict[str, Any]) -> dict[str, Any]:
    return calendar_client.list_calendars()


def _tool_get_events(args: dict[str, Any]) -> dict[str, Any]:
    return calendar_client.get_events(day=args["day"], all_calendars=True)


def _tool_find_free_slots(args: dict[str, Any]) -> dict[str, Any]:
    return calendar_client.find_free_slots(
        day=args["day"],
        duration_minutes=int(args.get("duration_minutes", 30)),
        earliest=args.get("earliest"),
        latest=args.get("latest"),
    )


def _tool_create_event(args: dict[str, Any]) -> dict[str, Any]:
    return calendar_client.create_event(
        summary=args["summary"],
        start=args["start"],
        end=args["end"],
        description=args.get("description"),
        calendar_id=args.get("calendar_id"),
        check_conflicts=True,
    )


def _tool_update_calendar_appearance(args: dict[str, Any]) -> dict[str, Any]:
    return calendar_client.update_calendar_appearance(
        args["calendar_id"],
        background_color=args.get("background_color"),
        foreground_color=args.get("foreground_color") or "#000000",
    )


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "get_preferences": _tool_get_preferences,
    "update_preferences": _tool_update_preferences,
    "list_calendars": _tool_list_calendars,
    "get_events": _tool_get_events,
    "find_free_slots": _tool_find_free_slots,
    "create_event": _tool_create_event,
    "update_calendar_appearance": _tool_update_calendar_appearance,
}


def dispatch_tool(name: str, arguments: str | dict[str, Any]) -> str:
    """Execute a tool and return a JSON string result for the model."""
    if name not in TOOL_HANDLERS:
        return json.dumps({"ok": False, "error": f"Unknown tool: {name}"})
    try:
        args = arguments if isinstance(arguments, dict) else json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return json.dumps({"ok": False, "error": "Invalid JSON arguments"})
    try:
        result = TOOL_HANDLERS[name](args)
    except FileNotFoundError as exc:
        result = {"ok": False, "error": str(exc), "auth_required": True}
    except Exception as exc:  # noqa: BLE001 - surface tool errors to the model
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return json.dumps(result, default=str)
