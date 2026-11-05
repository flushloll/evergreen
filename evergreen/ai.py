"""Optional: have Claude draft résumé highlights for newly added projects.

Only runs on projects that have no highlights yet, so your own wording is never replaced.
Requires `pip install "evergreen-cv[ai]"` and ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import sys
from typing import Any

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM = """You write résumé bullet points for software projects.
Use only facts stated in the material provided. Never invent metrics, users, awards or collaborators.
Each bullet starts with a strong past-tense verb, is one line (under 120 characters), and says what was
built and with what. If the material is too thin for a factual bullet, return fewer bullets."""

SCHEMA = {
    "type": "object",
    "properties": {"highlights": {"type": "array", "items": {"type": "string"}}},
    "required": ["highlights"],
    "additionalProperties": False,
}


def draft_highlights(project: dict[str, Any], readme: str, model: str = DEFAULT_MODEL,
                     max_bullets: int = 3, client: Any = None) -> list[str]:
    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    material = (f"Project: {project.get('name')}\nDescription: {project.get('description') or ''}\n"
                f"Tech: {', '.join(project.get('keywords', []))}\n\nREADME (truncated):\n{readme}")
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": f"Write up to {max_bullets} bullets.\n\n{material}"}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        return []
    text = next((b.text for b in response.content if b.type == "text"), "")
    return [h.strip() for h in json.loads(text).get("highlights", []) if h.strip()][:max_bullets]


def enrich(resume: dict[str, Any], added: list[dict[str, Any]], readme_for, cfg: dict[str, Any]) -> list[str]:
    """Fill highlights on newly added projects. Returns a change log."""
    changes = []
    by_name = {p.get("name"): p for p in resume.get("projects", [])}
    for item in added:
        entry = by_name.get(item["name"])
        if not entry or entry.get("highlights"):
            continue
        try:
            bullets = draft_highlights(item, readme_for(item), model=cfg.get("model", DEFAULT_MODEL),
                                       max_bullets=int(cfg.get("max_bullets", 3)))
        except Exception as exc:  # never fail a sync because the AI step did
            print(f"evergreen: skipped AI highlights for {item['name']}: {exc}", file=sys.stderr)
            continue
        if bullets:
            entry["highlights"] = bullets
            changes.append(f"projects: drafted {len(bullets)} highlights for {item['name']} (AI, please review)")
    return changes
