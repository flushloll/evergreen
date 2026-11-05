"""Read LinkedIn's official data export (Settings → Data privacy → Get a copy of your data).

No scraping: point Evergreen at the ZIP (or its unzipped folder) LinkedIn emails you.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any

from ..resume import iso_date


def _tables(path: str | Path) -> dict[str, list[dict[str, str]]]:
    p = Path(path)
    raw: dict[str, str] = {}
    if p.is_dir():
        for f in p.rglob("*.csv"):
            raw[f.name] = f.read_text(encoding="utf-8-sig")
    else:
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if name.endswith(".csv"):
                    raw[Path(name).name] = z.read(name).decode("utf-8-sig")
    tables = {}
    for name, text in raw.items():
        # Some export files start with a "Notes:" preamble before the header row.
        lines = text.splitlines()
        start = next((i for i, l in enumerate(lines) if "," in l and not l.startswith("Notes")), 0)
        tables[name] = [{k.strip(): (v or "").strip() for k, v in row.items() if k}
                        for row in csv.DictReader(io.StringIO("\n".join(lines[start:])))]
    return tables


def _drop_empty(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def collect(path: str | Path) -> dict[str, Any]:
    t = _tables(path)
    out: dict[str, Any] = {}

    if prof := (t.get("Profile.csv") or [None])[0]:
        name = " ".join(filter(None, [prof.get("First Name"), prof.get("Last Name")]))
        out["basics"] = _drop_empty({
            "name": name,
            "label": prof.get("Headline"),
            "summary": prof.get("Summary"),
            "location": {"city": prof["Geo Location"]} if prof.get("Geo Location") else None,
        })

    out["work"] = [_drop_empty({
        "name": r.get("Company Name"),
        "position": r.get("Title"),
        "location": r.get("Location"),
        "startDate": iso_date(r.get("Started On")),
        "endDate": iso_date(r.get("Finished On")),
        "summary": r.get("Description"),
    }) for r in t.get("Positions.csv", []) if r.get("Company Name")]

    out["education"] = [_drop_empty({
        "institution": r.get("School Name"),
        "studyType": r.get("Degree Name"),
        "startDate": iso_date(r.get("Start Date")),
        "endDate": iso_date(r.get("End Date")),
        "summary": r.get("Notes") or r.get("Activities"),
    }) for r in t.get("Education.csv", []) if r.get("School Name")]

    out["certificates"] = [_drop_empty({
        "name": r.get("Name"),
        "issuer": r.get("Authority"),
        "date": iso_date(r.get("Started On")),
        "url": r.get("Url"),
    }) for r in t.get("Certifications.csv", []) if r.get("Name")]

    out["skills"] = [r["Name"] for r in t.get("Skills.csv", []) if r.get("Name")]
    return out
