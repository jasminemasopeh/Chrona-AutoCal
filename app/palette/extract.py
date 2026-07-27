"""Extract a dominant color palette from an image, or invent a random shaded aesthetic."""

from __future__ import annotations

import colorsys
import random
from pathlib import Path

import numpy as np
from PIL import Image

_AESTHETIC_NAMES = [
    "coastal mist",
    "desert clay",
    "forest canopy",
    "midnight ink",
    "sunlit terracotta",
    "lavender dusk",
    "olive grove",
    "arctic glass",
    "copper ember",
    "sage studio",
]


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def generate_random_shaded_palette(*, num_colors: int = 5) -> dict:
    """
    Build a cohesive random aesthetic palette: one base hue with light→dark shades,
    plus a soft complementary accent.

    Returns {aesthetic_name, palette: [{hex, rgb, weight}, ...]}.
    """
    n = max(3, min(8, int(num_colors)))
    base_h = random.random()
    # Prefer mid saturation / avoid neon or muddy greys
    base_s = random.uniform(0.35, 0.72)
    aesthetic_name = random.choice(_AESTHETIC_NAMES)

    # Evenly spaced values from light to deep
    values = np.linspace(0.88, 0.28, num=max(1, n - 1))
    palette: list[dict] = []
    for i, v in enumerate(values):
        # Slight hue drift keeps shades related but not flat
        h = (base_h + (i - len(values) / 2) * 0.015) % 1.0
        s = min(0.85, max(0.2, base_s + (0.5 - v) * 0.15))
        r, g, b = colorsys.hsv_to_rgb(h, s, float(v))
        rgb = (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))
        palette.append(
            {
                "hex": _rgb_to_hex(rgb),
                "rgb": list(rgb),
                "weight": round(1.0 / n, 4),
            }
        )

    # Complementary accent at medium brightness
    accent_h = (base_h + 0.5) % 1.0
    ar, ag, ab = colorsys.hsv_to_rgb(accent_h, min(0.65, base_s + 0.05), 0.55)
    accent_rgb = (int(round(ar * 255)), int(round(ag * 255)), int(round(ab * 255)))
    palette.append(
        {
            "hex": _rgb_to_hex(accent_rgb),
            "rgb": list(accent_rgb),
            "weight": round(1.0 / n, 4),
        }
    )

    # Renormalize weights
    total = sum(p["weight"] for p in palette) or 1.0
    for p in palette:
        p["weight"] = round(p["weight"] / total, 4)

    return {"aesthetic_name": aesthetic_name, "palette": palette}


def extract_palette_from_image(
    image_path: str | Path,
    *,
    num_colors: int = 5,
    resize_to: int = 150,
) -> list[dict]:
    """
    Extract dominant colors via simple k-means on a downscaled image.

    Returns a list of {hex, rgb, weight} sorted by weight descending.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    img = Image.open(path).convert("RGB")
    img.thumbnail((resize_to, resize_to))
    pixels = np.asarray(img, dtype=np.float64).reshape(-1, 3)

    # Drop near-white / near-black extremes so UI palettes stay interesting
    luminances = 0.2126 * pixels[:, 0] + 0.7152 * pixels[:, 1] + 0.0722 * pixels[:, 2]
    mask = (luminances > 20) & (luminances < 245)
    filtered = pixels[mask] if mask.sum() > num_colors * 10 else pixels

    k = max(1, min(num_colors, len(filtered)))
    # Initialize centers by sampling evenly across brightness-sorted pixels
    order = np.argsort(filtered[:, 0] + filtered[:, 1] + filtered[:, 2])
    step = max(1, len(order) // k)
    centers = filtered[order[::step][:k]].copy()

    for _ in range(12):
        # Assign
        dists = ((filtered[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = dists.argmin(axis=1)
        new_centers = centers.copy()
        for i in range(k):
            members = filtered[labels == i]
            if len(members):
                new_centers[i] = members.mean(axis=0)
        if np.allclose(new_centers, centers):
            break
        centers = new_centers

    dists = ((filtered[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    labels = dists.argmin(axis=1)

    palette: list[dict] = []
    total = len(filtered)
    for i in range(k):
        count = int((labels == i).sum())
        if count == 0:
            continue
        rgb = tuple(int(round(c)) for c in centers[i])
        rgb = tuple(max(0, min(255, v)) for v in rgb)
        palette.append(
            {
                "hex": _rgb_to_hex(rgb),  # type: ignore[arg-type]
                "rgb": list(rgb),
                "weight": round(count / total, 4),
            }
        )

    palette.sort(key=lambda x: x["weight"], reverse=True)
    return palette


def parse_hex_list(text: str) -> list[str]:
    """Pull #RRGGBB colors out of free text."""
    import re

    found = re.findall(r"#?(?:[0-9a-fA-F]{6})", text)
    colors = []
    for item in found:
        h = item if item.startswith("#") else f"#{item}"
        colors.append(h.lower())
    # unique preserve order
    seen = set()
    out = []
    for c in colors:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out
