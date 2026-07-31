"""OpenAI/OpenRouter tool-calling agent loops for scheduling and palette styling."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.agent.prompts import PALETTE_SYSTEM_PROMPT, SYSTEM_PROMPT
from app.agent.tools import (
    PALETTE_TOOL_DEFINITIONS,
    SCHEDULE_TOOL_DEFINITIONS,
    dispatch_tool,
)
from app.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_APP_NAME,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
)
from app.palette.extract import parse_hex_list, generate_random_shaded_palette
from app.palette.map_colors import build_palette_context


def _client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your OpenRouter key."
        )
    return OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-Title": OPENROUTER_APP_NAME,
        },
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def suggest_hexes_from_description(description: str, n: int = 5) -> list[str]:
    """Ask the LLM for hex colors matching an aesthetic description."""
    existing = parse_hex_list(description)
    if len(existing) >= 2:
        return existing[:n]

    client = _client()
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        temperature=0.4,
        messages=[
            {
                "role": "system",
                "content": (
                    "Return ONLY a JSON array of 4-6 hex color strings (e.g. [\"#1a2b3c\", ...]) "
                    "that match the user's calendar aesthetic description. No markdown."
                ),
            },
            {"role": "user", "content": description},
        ],
    )
    content = response.choices[0].message.content or "[]"
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return [c if str(c).startswith("#") else f"#{c}" for c in data][:n]
    except json.JSONDecodeError:
        pass
    return parse_hex_list(content)[:n] or existing


def _run_tool_loop(
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    tools: list[dict[str, Any]],
    write_blocked_tools: set[str] | None = None,
    max_steps: int = 20,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, indent=2)},
    ]
    client = _client()
    tool_trace: list[dict[str, Any]] = []
    blocked = write_blocked_tools or set()

    for _ in range(max_steps):
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
        )
        message = response.choices[0].message
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": message.content,
        }
        if message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        messages.append(assistant_msg)

        if not message.tool_calls:
            parsed = _extract_json_object(message.content or "")
            return {
                "ok": True,
                "parsed": parsed or {},
                "raw_assistant_message": message.content,
                "tool_trace": tool_trace,
            }

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            args = tool_call.function.arguments
            if name in blocked:
                result = json.dumps(
                    {
                        "ok": False,
                        "error": f"{name} is disabled for this run (dry-run)",
                        "dry_run": True,
                    }
                )
            else:
                result = dispatch_tool(name, args)
            tool_trace.append({"tool": name, "arguments": args, "result": result[:2000]})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    return {
        "ok": False,
        "error": "Agent exceeded max tool steps without producing a final response.",
        "parsed": {},
        "tool_trace": tool_trace,
        "raw_assistant_message": None,
    }


def run_scheduling_agent(
    *,
    task_list: str,
    target_day: str,
    write_to_calendar: bool = True,
    max_steps: int = 20,
) -> dict[str, Any]:
    """Plan a conflict-free schedule; auto-detect calendar and time slot per task."""
    user_payload = {
        "target_day": target_day,
        "task_list": task_list,
        "write_to_calendar": write_to_calendar,
        "instructions": (
            "Automatically detect which calendar each task belongs on and where it fits "
            "in the day. Gym/health/personal tasks go on Personal — never Work. "
            + (
                "Create events on the matching calendars, then finish with the required JSON."
                if write_to_calendar
                else (
                    "Do NOT call create_event. Only propose calendar_id, times, and category "
                    "with event_id null so the user can accept/reject before writing."
                )
            )
        ),
    }
    blocked = set() if write_to_calendar else {"create_event"}
    result = _run_tool_loop(
        system_prompt=SYSTEM_PROMPT,
        user_payload=user_payload,
        tools=SCHEDULE_TOOL_DEFINITIONS,
        write_blocked_tools=blocked,
        max_steps=max_steps,
    )
    parsed = result.get("parsed") or {}
    return {
        "ok": result.get("ok", False),
        "error": result.get("error"),
        "summary": parsed.get("summary") or result.get("raw_assistant_message") or "",
        "proposals": parsed.get("proposals") or [],
        "raw_assistant_message": result.get("raw_assistant_message"),
        "tool_trace": result.get("tool_trace") or [],
    }


def run_palette_agent(
    *,
    aesthetic_description: str | None = None,
    style_preferences: str | None = None,
    image_palette: list[dict] | None = None,
    apply_changes: bool = True,
    max_steps: int = 16,
) -> dict[str, Any]:
    """Map a palette onto Google calendars (not events) using style preferences."""
    description_hexes: list[str] = []
    random_aesthetic: str | None = None
    used_random = False

    if aesthetic_description:
        description_hexes = suggest_hexes_from_description(aesthetic_description)

    # If the user provided no description and no image, invent a shaded aesthetic palette.
    if not aesthetic_description and not image_palette and not description_hexes:
        random_result = generate_random_shaded_palette(num_colors=5)
        image_palette = random_result["palette"]
        random_aesthetic = random_result["aesthetic_name"]
        used_random = True

    palette_ctx = build_palette_context(
        image_palette=image_palette,
        description_hexes=description_hexes or None,
    )

    # Prefer raw source hexes for calendar RGB colors (not just Google event colorIds)
    source_hexes: list[str] = []
    for item in palette_ctx.get("source_palette") or []:
        if isinstance(item, str):
            source_hexes.append(item if item.startswith("#") else f"#{item}")
        elif isinstance(item, dict) and item.get("hex"):
            source_hexes.append(item["hex"])
    if not source_hexes:
        source_hexes = [
            m.get("google_hex")
            for m in (palette_ctx.get("mapped_google_colors") or [])
            if m.get("google_hex")
        ]

    effective_aesthetic = aesthetic_description or (
        f"random {random_aesthetic} palette with harmonious shades" if random_aesthetic else None
    )

    user_payload = {
        "aesthetic_description": effective_aesthetic,
        "style_preferences": style_preferences,
        "generated_random_palette": used_random,
        "source_hex_palette": source_hexes,
        "palette_context": palette_ctx,
        "apply_changes": apply_changes,
        "instructions": (
            "Restyle the user's calendars (Personal/Work/School/etc.) using the palette. "
            "Honor style_preferences when provided (e.g. black text, mobile parity); "
            "if style_preferences are empty, default to readable dark text on lighter "
            "calendars and light text on deep backgrounds. "
            "Do not recolor individual events. Finish with the required JSON object."
        ),
    }
    blocked = set() if apply_changes else {"update_calendar_appearance"}
    result = _run_tool_loop(
        system_prompt=PALETTE_SYSTEM_PROMPT,
        user_payload=user_payload,
        tools=PALETTE_TOOL_DEFINITIONS,
        write_blocked_tools=blocked,
        max_steps=max_steps,
    )
    parsed = result.get("parsed") or {}
    summary = parsed.get("summary") or result.get("raw_assistant_message") or ""
    if used_random and random_aesthetic and summary:
        summary = f"Random “{random_aesthetic}” shades. {summary}"
    elif used_random and random_aesthetic:
        summary = f"Generated a random “{random_aesthetic}” shaded palette."

    return {
        "ok": result.get("ok", False),
        "error": result.get("error"),
        "summary": summary,
        "assignments": parsed.get("assignments") or [],
        "notes": parsed.get("notes") or [],
        "palette": palette_ctx,
        "source_hex_palette": source_hexes,
        "random_aesthetic": random_aesthetic,
        "raw_assistant_message": result.get("raw_assistant_message"),
        "tool_trace": result.get("tool_trace") or [],
    }
