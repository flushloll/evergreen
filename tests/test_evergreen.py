import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from evergreen import ai, cli, render
from evergreen import resume as R
from evergreen.merge import Merger
from evergreen.sources import github, linkedin

FIX = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------- dates
@pytest.mark.parametrize("raw,want", [
    ("Jan 2020", "2020-01"), ("September 2021", "2021-09"), ("2019", "2019"),
    ("2023-04-05T10:00:00Z", "2023-04"), ("03/2022", "2022-03"), ("", None), ("Present", None),
])
def test_iso_date(raw, want):
    assert R.iso_date(raw) == want


# ---------------------------------------------------------------- github
def fake_github(now="2026-11-01T00:00:00Z"):
    repos = [
        {"name": "octo", "full_name": "octo/octo", "description": "profile", "fork": False,
         "html_url": "https://github.com/octo/octocat", "pushed_at": now, "created_at": now},
        {"name": "rocket", "full_name": "octo/rocket", "description": "A tiny rocket sim", "fork": False,
         "html_url": "https://github.com/octo/rocket", "homepage": "https://rocket.dev",
         "stargazers_count": 40, "topics": ["physics"], "pushed_at": now, "created_at": "2024-02-01T00:00:00Z"},
        {"name": "old-thing", "full_name": "octo/old-thing", "description": "Archived experiment",
         "fork": False, "html_url": "https://github.com/octo/old-thing", "stargazers_count": 2,
         "pushed_at": "2021-05-01T00:00:00Z", "created_at": "2020-01-01T00:00:00Z"},
        {"name": "forked", "full_name": "octo/forked", "description": "x", "fork": True,
         "html_url": "https://github.com/octo/forked", "pushed_at": now},
        {"name": "nodesc", "full_name": "octo/nodesc", "description": None, "fork": False,
         "html_url": "https://github.com/octo/nodesc", "pushed_at": now},
    ]
    routes = {
        "/users/octo": {"name": "Octo Cat", "bio": "Builds things", "html_url": "https://github.com/octo",
                        "blog": "", "location": "Boston"},
        "/repos/octo/rocket/languages": {"Rust": 900, "Python": 100},
        "/repos/octo/old-thing/languages": {"Python": 500},
    }

    def fetch(path):
        if path.startswith("/users/octo/repos"):
            return repos
        if path.startswith("/search/issues"):
            assert "-user%3Aocto" in path
            return {"items": [{"repository_url": "https://api.github.com/repos/big/lib"}] * 3}
        return routes[path]

    return fetch


def test_github_collect_filters_and_ranks():
    snap = github.collect("octo", {"rank": "stars"}, fetch=fake_github())
    names = [p["name"] for p in snap["projects"]]
    assert names == ["rocket", "old-thing"]  # no fork, no profile repo, no description-less repo
    rocket, old = snap["projects"]
    assert rocket["url"] == "https://rocket.dev" and "endDate" not in rocket
    assert rocket["keywords"] == ["Rust", "Python", "physics"]
    assert old["endDate"] == "2021-05"
    assert snap["languages"] == ["Rust", "Python"]
    assert snap["contributions"] == [{"repo": "big/lib", "url": "https://github.com/big/lib", "count": 3}]
    assert snap["basics"]["location"] == {"city": "Boston"}


# ---------------------------------------------------------------- linkedin
def test_linkedin_collect_from_dir_and_zip(tmp_path):
    from_dir = linkedin.collect(FIX / "linkedin")
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in (FIX / "linkedin").iterdir():
            zf.write(f, f"Basic_LinkedInDataExport/{f.name}")
    assert linkedin.collect(z) == from_dir

    assert from_dir["basics"]["name"] == "Ada Lovelace"
    assert from_dir["work"][0] == {"name": "Analytical Engines Ltd", "position": "Programmer",
                                   "location": "London", "startDate": "1842-01", "endDate": "1843-09",
                                   "summary": "Wrote note G."}
    assert "endDate" not in from_dir["work"][1]
    assert from_dir["education"][0]["studyType"] == "BSc Mathematics"
    assert from_dir["skills"] == ["Mathematics", "Python"]
    assert from_dir["certificates"][0]["date"] == "1840-03"


def test_import_linkedin_copies_only_resume_files(tmp_path):
    cli.import_linkedin(FIX / "linkedin", tmp_path / "li")
    assert sorted(p.name for p in (tmp_path / "li").iterdir()) == sorted(cli.LINKEDIN_FILES)


# ---------------------------------------------------------------- merge
def test_merge_never_overwrites_and_deletions_stick():
    snap = github.collect("octo", {}, fetch=fake_github())
    resume = {"basics": {"name": "Ada Custom", "summary": ""},
              "projects": [{"name": "rocket", "description": "My own words", "keywords": ["rust"]}]}
    m = Merger(resume)
    added = m.github(snap)

    rocket = resume["projects"][0]
    assert rocket["description"] == "My own words"          # human text kept
    assert rocket["keywords"] == ["rust", "Python", "physics"]  # unioned, case-insensitive
    assert resume["basics"]["name"] == "Ada Custom"
    assert resume["basics"]["summary"] == "Builds things"    # empty field filled
    assert [a["name"] for a in added] == ["old-thing"]
    assert all("repo" not in p and "stars" not in p for p in resume["projects"])
    contrib = next(p for p in resume["projects"] if p.get("type") == "open-source")
    assert contrib["highlights"] == ["Merged 3 pull requests into big/lib"]

    # user deletes old-thing; next sync must not re-add it, and is otherwise a no-op
    resume["projects"] = [p for p in resume["projects"] if p["name"] != "old-thing"]
    m2 = Merger(resume)
    assert m2.github(snap) == [] and m2.changes == []


def test_merge_linkedin_idempotent():
    snap = linkedin.collect(FIX / "linkedin")
    resume = {}
    m = Merger(resume)
    m.linkedin(snap)
    assert len(resume["work"]) == 2 and resume["skills"][0]["name"] == "Skills"
    m2 = Merger(resume)
    m2.linkedin(snap)
    assert m2.changes == []


# ---------------------------------------------------------------- ai
class FakeClient:
    def __init__(self, payload, stop="end_turn"):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.payload, self.stop = payload, stop

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason=self.stop,
                               content=[SimpleNamespace(type="text", text=json.dumps(self.payload))])


def test_ai_draft_highlights_request_shape():
    client = FakeClient({"highlights": ["Built a rocket sim in Rust", " ", "B", "C", "D"]})
    out = ai.draft_highlights({"name": "rocket", "keywords": ["Rust"]}, "# Rocket", client=client)
    assert out == ["Built a rocket sim in Rust", "B", "C"]
    kw = client.calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["fallbacks"] == "default"


def test_ai_refusal_returns_nothing():
    assert ai.draft_highlights({"name": "x"}, "", client=FakeClient({}, stop="refusal")) == []


# ---------------------------------------------------------------- render + cli
def test_render_and_cli_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init", "--github", "octo", "--linkedin", str(FIX / "linkedin")])
    assert (tmp_path / ".github/workflows/evergreen.yml").exists()
    monkeypatch.setattr(github, "http_fetch", lambda token=None: fake_github())
    cli.main(["sync"])
    data = R.load("resume.yaml")
    assert data["basics"]["name"] == "Octo Cat"  # GitHub ran first and filled the empty name
    assert {w["name"] for w in data["work"]} == {"Analytical Engines Ltd", "Babbage Labs"}
    cli.main(["render", "--formats", "md,html"])
    md = (tmp_path / "dist/resume.md").read_text()
    html = (tmp_path / "dist/resume.html").read_text()
    assert "## Experience" in md and "Jan 1842 – Sep 1843" in md and "Oct 1843 – Present" in md
    assert html.startswith("<!DOCTYPE html>") and "Babbage Labs" in html
