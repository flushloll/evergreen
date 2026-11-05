"""Render a JSON Resume to Markdown, print-ready HTML, and PDF (via headless Chrome if present)."""

from __future__ import annotations

import html
import shutil
import subprocess
from pathlib import Path
from typing import Any

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def fmt_date(d: str | None) -> str:
    if not d:
        return ""
    parts = str(d).split("-")
    if len(parts) >= 2 and parts[1].isdigit() and 1 <= int(parts[1]) <= 12:
        return f"{MONTHS[int(parts[1]) - 1]} {parts[0]}"
    return parts[0]


def span(item: dict[str, Any]) -> str:
    start, end = fmt_date(item.get("startDate")), fmt_date(item.get("endDate"))
    if not start:
        return end
    return f"{start} – {end or 'Present'}"


def _entries(r: dict[str, Any]):
    """Yield (section title, [(title, subtitle, dates, url, summary, bullets)])."""
    work = [(w.get("position", ""), w.get("name", ""), span(w), w.get("url"), w.get("summary"),
             w.get("highlights", [])) for w in r.get("work", [])]
    edu = [(e.get("institution", ""), " · ".join(filter(None, [e.get("studyType"), e.get("area")])),
            span(e), e.get("url"), e.get("summary"), e.get("courses", [])) for e in r.get("education", [])]
    proj = [(p.get("name", ""), " · ".join(p.get("keywords", [])), span(p), p.get("url"),
             p.get("description"), p.get("highlights", [])) for p in r.get("projects", [])]
    certs = [(c.get("name", ""), c.get("issuer", ""), fmt_date(c.get("date")), c.get("url"), None, [])
             for c in r.get("certificates", [])]
    for title, items in [("Experience", work), ("Education", edu), ("Projects", proj), ("Certifications", certs)]:
        if items:
            yield title, items


def _contact(b: dict[str, Any]) -> list[tuple[str, str | None]]:
    loc = b.get("location") or {}
    out = [(b.get("email"), f"mailto:{b['email']}" if b.get("email") else None),
           (b.get("phone"), None),
           (", ".join(filter(None, [loc.get("city"), loc.get("region")])) or None, None),
           (b.get("url"), b.get("url"))]
    out += [(p.get("url") or p.get("username"), p.get("url")) for p in b.get("profiles", [])]
    return [(t.removeprefix("https://").removeprefix("http://"), u) for t, u in out if t]


def to_markdown(r: dict[str, Any]) -> str:
    b = r.get("basics", {})
    lines = [f"# {b.get('name', 'Your Name')}"]
    if b.get("label"):
        lines.append(f"**{b['label']}**")
    contact = [f"[{t}]({u})" if u else t for t, u in _contact(b)]
    if contact:
        lines.append(" · ".join(contact))
    if b.get("summary"):
        lines += ["", b["summary"]]
    for title, items in _entries(r):
        lines += ["", f"## {title}"]
        for name, sub, dates, url, summary, bullets in items:
            head = f"[{name}]({url})" if url else name
            lines += ["", f"### {head}" + (f" — {sub}" if sub else "") + (f"  \n*{dates}*" if dates else "")]
            if summary:
                lines.append(summary)
            lines += [f"- {x}" for x in bullets]
    skills = r.get("skills", [])
    if skills:
        lines += ["", "## Skills", ""]
        lines += [f"- **{s.get('name')}:** {', '.join(s.get('keywords', []))}" for s in skills]
    return "\n".join(lines).strip() + "\n"


CSS = """
:root { --ink:#1b1f23; --muted:#5b6470; --accent:#1f7a4d; --rule:#d9dee3; }
* { box-sizing:border-box; }
body { margin:0; background:#fff; color:var(--ink); font:10.5pt/1.45 "Inter","Helvetica Neue",Arial,sans-serif; }
main { max-width:8.5in; margin:0 auto; padding:0.55in 0.6in; }
h1 { font-size:22pt; margin:0; letter-spacing:-0.01em; }
.label { color:var(--accent); font-weight:600; margin-top:2px; }
.contact { color:var(--muted); font-size:9.5pt; margin:6px 0 0; }
.contact a { color:inherit; text-decoration:none; }
.contact span + span::before { content:"·"; margin:0 6px; }
h2 { font-size:10pt; text-transform:uppercase; letter-spacing:0.08em; color:var(--accent);
     border-bottom:1px solid var(--rule); padding-bottom:3px; margin:16px 0 6px; }
.item { margin:7px 0; break-inside:avoid; }
.row { display:flex; justify-content:space-between; gap:12px; }
.row b a { color:inherit; text-decoration:none; }
.sub { color:var(--muted); }
.dates { color:var(--muted); white-space:nowrap; font-size:9.5pt; }
ul { margin:3px 0 0; padding-left:16px; }
li { margin:1px 0; }
p { margin:3px 0; }
@page { size:letter; margin:0; }
@media print { main { padding:0.45in 0.55in; } }
"""


def to_html(r: dict[str, Any]) -> str:
    e = html.escape
    b = r.get("basics", {})

    def link(text: str, url: str | None) -> str:
        return f'<a href="{e(url)}">{e(text)}</a>' if url else e(text)

    body = [f"<h1>{e(b.get('name', 'Your Name'))}</h1>"]
    if b.get("label"):
        body.append(f'<div class="label">{e(b["label"])}</div>')
    contact = "".join(f"<span>{link(t, u)}</span>" for t, u in _contact(b))
    if contact:
        body.append(f'<p class="contact">{contact}</p>')
    if b.get("summary"):
        body.append(f"<p>{e(b['summary'])}</p>")
    for title, items in _entries(r):
        body.append(f"<h2>{e(title)}</h2>")
        for name, sub, dates, url, summary, bullets in items:
            sub_html = f' <span class="sub">— {e(sub)}</span>' if sub else ""
            body.append(f'<div class="item"><div class="row"><div><b>{link(name, url)}</b>{sub_html}</div>'
                        f'<div class="dates">{e(dates)}</div></div>')
            if summary:
                body.append(f"<p>{e(summary)}</p>")
            if bullets:
                body.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in bullets) + "</ul>")
            body.append("</div>")
    if r.get("skills"):
        body.append("<h2>Skills</h2>")
        body += [f"<p><b>{e(s.get('name', ''))}:</b> {e(', '.join(s.get('keywords', [])))}</p>"
                 for s in r["skills"]]
    title = e(b.get("name", "Résumé"))
    return (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{title} — Résumé</title><style>{CSS}</style></head>"
            f"<body><main>{''.join(body)}</main></body></html>\n")


def find_chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if path := shutil.which(name):
            return path
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return mac if Path(mac).exists() else None


def to_pdf(html_path: Path, pdf_path: Path) -> bool:
    chrome = find_chrome()
    if not chrome:
        return False
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri()],
                   check=True, capture_output=True, timeout=120)
    return pdf_path.exists()


def render(r: dict[str, Any], out_dir: str | Path, formats: list[str], stem: str = "resume") -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    if "md" in formats:
        (p := out / f"{stem}.md").write_text(to_markdown(r), encoding="utf-8")
        written.append(p)
    if "html" in formats or "pdf" in formats:
        (h := out / f"{stem}.html").write_text(to_html(r), encoding="utf-8")
        if "html" in formats:
            written.append(h)
        if "pdf" in formats:
            if to_pdf(h, p := out / f"{stem}.pdf"):
                written.append(p)
            else:
                print("evergreen: no Chrome/Chromium found, skipped PDF")
    return written
