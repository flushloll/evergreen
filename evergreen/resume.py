"""Loading, saving and small helpers for a JSON Resume document kept as YAML."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def load(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p} must contain a mapping at the top level")
    return data


def dump(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def save(path: str | Path, data: dict[str, Any]) -> None:
    Path(path).write_text(dump(data), encoding="utf-8")


def iso_date(value: str | None) -> str | None:
    """Normalise 'Jan 2020', '2020', '2020-01-15T..' or '01/2020' to 'YYYY-MM' (or 'YYYY')."""
    if not value:
        return None
    v = value.strip()
    if not v or v.lower() in {"present", "now"}:
        return None
    if m := re.match(r"^(\d{4})-(\d{2})", v):
        return f"{m[1]}-{m[2]}"
    if m := re.match(r"^([A-Za-z]{3})[a-z]*\.? (\d{4})$", v):
        month = MONTHS.get(m[1].lower())
        if month:
            return f"{m[2]}-{month:02d}"
    if m := re.match(r"^(\d{1,2})/(\d{4})$", v):
        return f"{m[2]}-{int(m[1]):02d}"
    if re.match(r"^\d{4}$", v):
        return v
    return None


def section(resume: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Return resume[name] as a list, creating it if needed."""
    items = resume.get(name)
    if not isinstance(items, list):
        items = []
        resume[name] = items
    return items


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
