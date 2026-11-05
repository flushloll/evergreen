"""Pull profile, top repositories, languages and merged outside PRs from the GitHub REST API."""

from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..resume import iso_date

API = "https://api.github.com"
Fetch = Callable[[str], Any]


def http_fetch(token: str | None = None) -> Fetch:
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    def fetch(path: str) -> Any:
        req = urllib.request.Request(API + path, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "evergreen-cv",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)

    return fetch


def collect(username: str, cfg: dict[str, Any] | None = None, fetch: Fetch | None = None) -> dict[str, Any]:
    cfg = cfg or {}
    fetch = fetch or http_fetch()
    max_projects = int(cfg.get("max_projects", 6))
    min_stars = int(cfg.get("min_stars", 0))
    exclude = {e.lower() for e in cfg.get("exclude", [])}
    need_desc = bool(cfg.get("require_description", True))
    rank = cfg.get("rank", "recent")

    user = fetch(f"/users/{username}")
    basics: dict[str, Any] = {
        "name": user.get("name"),
        "url": user.get("blog") or None,
        "summary": user.get("bio"),
        "location": {"city": user["location"]} if user.get("location") else None,
        "profiles": [{"network": "GitHub", "username": username, "url": user.get("html_url")}],
    }

    repos: list[dict[str, Any]] = []
    for page in range(1, 4):
        batch = fetch(f"/users/{username}/repos?type=owner&sort=pushed&per_page=100&page={page}")
        repos += batch
        if len(batch) < 100:
            break

    def keep(r: dict[str, Any]) -> bool:
        return not (r.get("fork") or r.get("private") or r["name"].lower() in exclude
                    or r["name"].lower() == username.lower()  # profile README repo
                    or r.get("stargazers_count", 0) < min_stars
                    or (need_desc and not r.get("description")))

    candidates = [r for r in repos if keep(r)]
    if rank == "stars":
        candidates.sort(key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at", "")), reverse=True)
    else:
        candidates.sort(key=lambda r: r.get("pushed_at", ""), reverse=True)

    recent = (datetime.now(timezone.utc) - timedelta(days=int(cfg.get("active_days", 120)))).isoformat()
    projects, lang_bytes = [], Counter()
    for r in candidates[:max_projects]:
        langs = fetch(f"/repos/{r['full_name']}/languages") or {}
        lang_bytes.update(langs)
        project = {
            "name": r["name"],
            "description": r.get("description"),
            "url": r.get("homepage") or r["html_url"],
            "repo": r["html_url"],
            "keywords": list(langs)[:4] + [t for t in r.get("topics", []) if t not in {l.lower() for l in langs}][:4],
            "startDate": iso_date(r.get("created_at")),
            "stars": r.get("stargazers_count", 0),
        }
        if (r.get("pushed_at") or "") < recent:
            project["endDate"] = iso_date(r.get("pushed_at"))
        projects.append(project)

    contributions = []
    if cfg.get("include_contributions", True):
        q = urllib.parse.quote(f"author:{username} type:pr is:merged -user:{username}")
        found = fetch(f"/search/issues?q={q}&per_page=100").get("items", [])
        counts = Counter(i["repository_url"].removeprefix(f"{API}/repos/") for i in found)
        contributions = [{"repo": repo, "url": f"https://github.com/{repo}", "count": n}
                         for repo, n in counts.most_common(int(cfg.get("max_contributions", 5)))]

    return {
        "basics": {k: v for k, v in basics.items() if v},
        "projects": projects,
        "contributions": contributions,
        "languages": [lang for lang, _ in lang_bytes.most_common(int(cfg.get("max_languages", 8)))],
    }


def readme(full_name: str, fetch: Fetch | None = None, limit: int = 6000) -> str:
    """Return the start of a repository README, or '' if it has none."""
    fetch = fetch or http_fetch()
    try:
        data = fetch(f"/repos/{full_name}/readme")
    except Exception:
        return ""
    return base64.b64decode(data.get("content", "")).decode("utf-8", "replace")[:limit]
