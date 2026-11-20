"""تباين WCAG 2.2: دوال نقية (مأخوذة من sma-design/scripts/check-contrast.py)."""
from __future__ import annotations

import re

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    m = HEX_RE.match(hex_str.strip())
    if not m:
        raise ValueError(f"لون غير صالح: {hex_str!r}")
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _channel(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_str: str) -> float:
    r, g, b = hex_to_rgb(hex_str)
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def passes(ratio: float, *, text: bool) -> bool:
    return ratio >= (4.5 if text else 3.0)
