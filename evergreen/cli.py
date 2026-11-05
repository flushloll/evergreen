"""evergreen: init · import-linkedin · sync · render"""

from __future__ import annotations

import argparse
import copy
import sys
import zipfile
from pathlib import Path
from typing import Any

import yaml

from . import __version__, resume as R
from .merge import Merger
from .render import render

LINKEDIN_FILES = ["Profile.csv", "Positions.csv", "Education.csv", "Skills.csv", "Certifications.csv"]

CONFIG_TEMPLATE = """\
# Evergreen config: https://github.com/flushloll/evergreen
resume: resume.yaml

github:
  username: {github}
  max_projects: 6          # how many of your repos to feature
  rank: recent             # recent | stars
  min_stars: 0
  require_description: true
  include_contributions: true  # merged PRs to other people's repos
  exclude: []              # repo names to never add

linkedin:
  export: {linkedin}       # folder made by `evergreen import-linkedin`, or leave blank

ai:
  enabled: false           # Claude drafts bullets for new projects (needs ANTHROPIC_API_KEY)
  model: claude-opus-5-5
  max_bullets: 3

render:
  out: dist
  formats: [md, html, pdf]
"""

WORKFLOW_TEMPLATE = """\
name: evergreen
on:
  schedule: [{cron: "0 9 * * 1"}]   # Mondays 09:00 UTC
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: flushloll/evergreen@main
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}   # optional
"""

STARTER_RESUME = {
    "basics": {"name": "", "label": "", "email": "", "summary": "", "profiles": []},
    "work": [], "education": [], "projects": [], "skills": [],
}


def load_config(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        sys.exit(f"evergreen: {p} not found. Run `evergreen init` first.")
    cfg = yaml.safe_load(p.read_text()) or {}
    cfg["_root"] = p.resolve().parent
    return cfg


def cmd_init(a: argparse.Namespace) -> None:
    root = Path(a.dir)
    files = {
        root / "evergreen.yml": CONFIG_TEMPLATE.format(github=a.github or "your-github-username",
                                                       linkedin="linkedin" if a.linkedin else "''"),
        root / ".github/workflows/evergreen.yml": WORKFLOW_TEMPLATE,
        root / "resume.yaml": R.dump(STARTER_RESUME),
    }
    for path, text in files.items():
        if path.exists():
            print(f"  kept     {path}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"  created  {path}")
    if a.linkedin:
        import_linkedin(a.linkedin, root / "linkedin")
    print("\nNext: evergreen sync && evergreen render")


def import_linkedin(src: str | Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    src = Path(src)
    if src.is_dir():
        found = {f.name: f.read_bytes() for f in src.rglob("*.csv") if f.name in LINKEDIN_FILES}
    else:
        with zipfile.ZipFile(src) as z:
            found = {Path(n).name: z.read(n) for n in z.namelist() if Path(n).name in LINKEDIN_FILES}
    for name, data in found.items():
        (dest / name).write_bytes(data)
    print(f"  copied   {', '.join(sorted(found)) or 'nothing'} → {dest}/")
    print("  (only these files are kept; messages, connections etc. stay out of your repo)")


def cmd_import_linkedin(a: argparse.Namespace) -> None:
    import_linkedin(a.export, Path(a.dest))


def cmd_sync(a: argparse.Namespace) -> None:
    cfg = load_config(a.config)
    root = cfg["_root"]
    resume_path = root / cfg.get("resume", "resume.yaml")
    data = R.load(resume_path) or copy.deepcopy(STARTER_RESUME)
    merger = Merger(data)

    gh = cfg.get("github") or {}
    added: list[dict[str, Any]] = []
    if gh.get("username") and gh["username"] != "your-github-username":
        from .sources import github
        added = merger.github(github.collect(gh["username"], gh))
        ai = cfg.get("ai") or {}
        if added and (ai.get("enabled") or a.ai):
            from . import ai as ai_mod
            merger.changes += ai_mod.enrich(
                data, added, lambda p: github.readme(p["repo"].removeprefix("https://github.com/")), ai)

    li = (cfg.get("linkedin") or {}).get("export")
    if li:
        from .sources import linkedin
        path = root / li
        if path.exists():
            merger.linkedin(linkedin.collect(path))
        else:
            print(f"evergreen: LinkedIn export {path} not found, skipping", file=sys.stderr)

    report = "\n".join(f"- {c}" for c in merger.changes) or "- no changes"
    print(report)
    if a.changes_file:
        Path(a.changes_file).write_text(report + "\n")
    if not a.dry_run and merger.changes:
        R.save(resume_path, data)
        print(f"\nupdated {resume_path}")


def cmd_render(a: argparse.Namespace) -> None:
    cfg = load_config(a.config)
    root = cfg["_root"]
    rc = cfg.get("render") or {}
    data = R.load(root / cfg.get("resume", "resume.yaml"))
    formats = a.formats.split(",") if a.formats else rc.get("formats", ["md", "html", "pdf"])
    for p in render(data, root / rc.get("out", "dist"), formats):
        print(f"  wrote    {p}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="evergreen", description="Keep your résumé fresh from GitHub and LinkedIn.")
    ap.add_argument("--version", action="version", version=f"evergreen {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="scaffold evergreen.yml, resume.yaml and a weekly GitHub Action")
    p.add_argument("--github", help="your GitHub username")
    p.add_argument("--linkedin", help="path to your LinkedIn data export ZIP")
    p.add_argument("--dir", default=".")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("import-linkedin", help="copy just the résumé CSVs out of a LinkedIn export")
    p.add_argument("export")
    p.add_argument("--dest", default="linkedin")
    p.set_defaults(fn=cmd_import_linkedin)

    p = sub.add_parser("sync", help="pull sources and merge them into resume.yaml")
    p.add_argument("-c", "--config", default="evergreen.yml")
    p.add_argument("--dry-run", action="store_true", help="show changes without writing")
    p.add_argument("--ai", action="store_true", help="draft bullets for new projects with Claude")
    p.add_argument("--changes-file", help="also write the change list here (used for PR bodies)")
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("render", help="render resume.yaml to Markdown, HTML and PDF")
    p.add_argument("-c", "--config", default="evergreen.yml")
    p.add_argument("--formats", help="comma list: md,html,pdf")
    p.set_defaults(fn=cmd_render)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
