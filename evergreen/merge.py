"""Merge source snapshots into a resume without ever overwriting what a human wrote.

Rules
- Scalar fields are only filled when empty.
- Keyword lists are unioned (existing order first).
- Every entry Evergreen adds is remembered in meta.evergreen.seen, so deleting it sticks.
- The "Open-source contributions" project (type: open-source) is fully managed and rewritten.
"""

from __future__ import annotations

from typing import Any, Callable

from .resume import norm, section

CONTRIB_TYPE = "open-source"
PRIVATE_KEYS = {"repo", "stars"}  # carried by snapshots for internal use, never written


class Merger:
    def __init__(self, resume: dict[str, Any]):
        self.resume = resume
        meta = resume.setdefault("meta", {}).setdefault("evergreen", {})
        self.seen: list[str] = meta.setdefault("seen", [])
        self.changes: list[str] = []

    # -- helpers ---------------------------------------------------------
    def _fill(self, target: dict[str, Any], src: dict[str, Any], label: str) -> None:
        for k, v in src.items():
            if k in PRIVATE_KEYS or v in (None, "", [], {}):
                continue
            if k == "keywords":
                cur = target.setdefault("keywords", [])
                new = [x for x in v if norm(x) not in {norm(c) for c in cur}]
                if new:
                    cur.extend(new)
                    self.changes.append(f"{label}: +keywords {', '.join(new)}")
            elif target.get(k) in (None, "", [], {}):
                target[k] = v
                self.changes.append(f"{label}: set {k}")

    def _upsert(self, name: str, items: list[dict[str, Any]], key: Callable[[dict[str, Any]], str],
                label: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
        existing = section(self.resume, name)
        index = {key(e): e for e in existing}
        added = []
        for item in items:
            k = key(item)
            if not k.strip(":"):
                continue
            if k in index:
                self._fill(index[k], item, label(item))
            elif f"{name}:{k}" not in self.seen:
                entry = {kk: vv for kk, vv in item.items() if kk not in PRIVATE_KEYS}
                existing.append(entry)
                index[k] = entry
                self.seen.append(f"{name}:{k}")
                self.changes.append(f"{name}: added {label(item)}")
                added.append(item)
        return added

    # -- sources ---------------------------------------------------------
    def basics(self, src: dict[str, Any]) -> None:
        basics = self.resume.setdefault("basics", {})
        profiles = basics.setdefault("profiles", [])
        for p in src.get("profiles", []):
            if not any(norm(x.get("network")) == norm(p["network"]) for x in profiles):
                profiles.append(p)
                self.changes.append(f"basics: added {p['network']} profile")
        self._fill(basics, {k: v for k, v in src.items() if k != "profiles"}, "basics")

    def github(self, snap: dict[str, Any]) -> list[dict[str, Any]]:
        self.basics(snap.get("basics", {}))

        def pkey(p: dict[str, Any]) -> str:
            return norm(p.get("name"))

        added = self._upsert("projects", snap.get("projects", []), pkey, lambda p: p["name"])

        projects = section(self.resume, "projects")
        contribs = snap.get("contributions", [])
        current = next((p for p in projects if p.get("type") == CONTRIB_TYPE), None)
        if contribs:
            highlights = [f"Merged {c['count']} pull request{'s' * (c['count'] > 1)} into {c['repo']}"
                          for c in contribs]
            if current is None:
                current = {"name": "Open-source contributions", "type": CONTRIB_TYPE}
                projects.append(current)
            if current.get("highlights") != highlights:
                current["highlights"] = highlights
                self.changes.append("projects: refreshed open-source contributions")

        if snap.get("languages"):
            self.skills("Languages", snap["languages"])
        return added

    def skills(self, group: str, names: list[str]) -> None:
        skills = section(self.resume, "skills")
        entry = next((s for s in skills if norm(s.get("name")) == norm(group)), None)
        if entry is None:
            entry = {"name": group, "keywords": []}
            skills.append(entry)
        self._fill(entry, {"keywords": names}, f"skills/{group}")

    def linkedin(self, snap: dict[str, Any]) -> None:
        self.basics(snap.get("basics", {}))
        self._upsert("work", snap.get("work", []),
                     lambda w: f"{norm(w.get('name'))}:{norm(w.get('position'))}",
                     lambda w: f"{w.get('position')} @ {w.get('name')}")
        self._upsert("education", snap.get("education", []),
                     lambda e: f"{norm(e.get('institution'))}:{norm(e.get('studyType'))}",
                     lambda e: e.get("institution", ""))
        self._upsert("certificates", snap.get("certificates", []),
                     lambda c: norm(c.get("name")), lambda c: c.get("name", ""))
        if snap.get("skills"):
            self.skills("Skills", snap["skills"])
