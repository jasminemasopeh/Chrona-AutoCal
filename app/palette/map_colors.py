"""Map arbitrary hex colors onto Google Calendar event colorIds."""

from __future__ import annotations

import colorsys
from typing import Any

# Official-ish Google Calendar event colors (approximate hex for matching).
GOOGLE_EVENT_COLORS: dict[str, dict[str, str]] = {
    "1": {"name": "Lavender", "hex": "#7986cb"},
    "2": {"name": "Sage", "hex": "#33b679"},
    "3": {"name": "Grape", "hex": "#8e24aa"},
    "4": {"name": "Flamingo", "hex": "#e67c73"},
    "5": {"name": "Banana", "hex": "#f6bf26"},
    "6": {"name": "Tangerine", "hex": "#f4511e"},
    "7": {"name": "Peacock", "hex": "#039be5"},
    "8": {"name": "Graphite", "hex": "#616161"},
    "9": {"name": "Blueberry", "hex": "#3f51b5"},
    "10": {"name": "Basil", "hex": "#0b8043"},
    "11": {"name": "Tomato", "hex": "#d50000"},
}

DEFAULT_CATEGORIES = ["work", "personal", "health", "errands", "other"]


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _color_distance(hex_a: str, hex_b: str) -> float:
    """Perceptual-ish distance in HSV space."""
    r1, g1, b1 = _hex_to_rgb(hex_a)
    r2, g2, b2 = _hex_to_rgb(hex_b)
    h1, s1, v1 = colorsys.rgb_to_hsv(r1, g1, b1)
    h2, s2, v2 = colorsys.rgb_to_hsv(r2, g2, b2)
    dh = min(abs(h1 - h2), 1 - abs(h1 - h2))
    return (dh * 2) ** 2 + (s1 - s2) ** 2 + (v1 - v2) ** 2


def nearest_google_color(hex_color: str) -> dict[str, str]:
    best_id = "1"
    best_dist = float("inf")
    for color_id, meta in GOOGLE_EVENT_COLORS.items():
        dist = _color_distance(hex_color, meta["hex"])
        if dist < best_dist:
            best_dist = dist
            best_id = color_id
    meta = GOOGLE_EVENT_COLORS[best_id]
    return {
        "colorId": best_id,
        "name": meta["name"],
        "google_hex": meta["hex"],
        "source_hex": hex_color if hex_color.startswith("#") else f"#{hex_color}",
    }


def map_palette_to_google(palette: list[dict] | list[str]) -> list[dict[str, Any]]:
    """Map extracted palette entries (dicts with hex, or hex strings) to Google colors."""
    mapped: list[dict[str, Any]] = []
    used: set[str] = set()
    hexes: list[str] = []
    for item in palette:
        if isinstance(item, str):
            hexes.append(item if item.startswith("#") else f"#{item}")
        else:
            hexes.append(item["hex"])

    for hex_color in hexes:
        match = nearest_google_color(hex_color)
        # Prefer unique Google colors when possible
        if match["colorId"] in used:
            # try next-best unused
            ranked = sorted(
                GOOGLE_EVENT_COLORS.items(),
                key=lambda kv: _color_distance(hex_color, kv[1]["hex"]),
            )
            for color_id, meta in ranked:
                if color_id not in used:
                    match = {
                        "colorId": color_id,
                        "name": meta["name"],
                        "google_hex": meta["hex"],
                        "source_hex": hex_color,
                    }
                    break
        used.add(match["colorId"])
        mapped.append(match)
    return mapped


def assign_categories_to_palette(
    mapped_colors: list[dict[str, Any]],
    categories: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Pair categories with mapped Google colors in order.
    Extra colors are ignored; extra categories cycle colors.
    """
    cats = categories or DEFAULT_CATEGORIES
    if not mapped_colors:
        # Fallback defaults
        fallback_ids = ["9", "2", "7", "6", "8"]
        mapped_colors = [
            {
                "colorId": fallback_ids[i % len(fallback_ids)],
                "name": GOOGLE_EVENT_COLORS[fallback_ids[i % len(fallback_ids)]]["name"],
                "google_hex": GOOGLE_EVENT_COLORS[fallback_ids[i % len(fallback_ids)]]["hex"],
                "source_hex": GOOGLE_EVENT_COLORS[fallback_ids[i % len(fallback_ids)]]["hex"],
            }
            for i in range(len(cats))
        ]

    assignment: dict[str, dict[str, Any]] = {}
    for i, cat in enumerate(cats):
        color = mapped_colors[i % len(mapped_colors)]
        assignment[cat] = color
    return assignment


def build_palette_context(
    *,
    image_palette: list[dict] | None = None,
    description_hexes: list[str] | None = None,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """Combine image and/or description colors into a category→colorId map."""
    source_colors: list[Any] = []
    if image_palette:
        source_colors.extend(image_palette)
    if description_hexes:
        source_colors.extend(description_hexes)

    mapped = map_palette_to_google(source_colors) if source_colors else []
    assignment = assign_categories_to_palette(mapped, categories=categories)
    return {
        "source_palette": source_colors,
        "mapped_google_colors": mapped,
        "category_colors": assignment,
    }


def categorize_task(title: str, description: str = "") -> str:
    """Lightweight keyword categorization for coloring."""
    text = f"{title} {description}".lower()
    rules = [
        ("health", ["gym", "run", "yoga", "workout", "doctor", "health", "meditat", "walk"]),
        ("errands", ["errand", "grocery", "shop", "bank", "pickup", "laundry", "clean"]),
        ("personal", ["personal", "family", "friend", "hobby", "read", "game", "movie"]),
        ("work", ["work", "meeting", "email", "project", "report", "code", "study", "class", "homework"]),
    ]
    for category, keywords in rules:
        if any(k in text for k in keywords):
            return category
    return "other"
