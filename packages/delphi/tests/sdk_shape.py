"""SDK 2.1.0 shapes the plugin locks. node_modules is gitignored."""
from __future__ import annotations

import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
EXCERPT = Path(__file__).resolve().parent / "fixtures" / "sdk_2_1_0_shape.d.ts"
_NULL = re.compile(r"(\w+):\s*\w+\[\]\s*\|\s*null")


def null_names(text):
    return set(_NULL.findall(text))


def market_declares_string_error(text):
    if "export interface Market {" not in text:
        return False
    body = text.split("export interface Market {", 1)[1].split("\n}", 1)[0]
    return "error: string | null;" in body


def recorded_text():
    return EXCERPT.read_text()


def live_types_text():
    """Concatenated installed declarations, or None when the SDK is not installed."""
    root = PACKAGE / "node_modules" / "@gensyn-ai" / "gensyn-delphi-sdk" / "dist"
    if not root.is_dir():
        return None
    parts = [path.read_text() for path in sorted(root.rglob("*.d.ts"))]
    return "\n".join(parts) if parts else None
