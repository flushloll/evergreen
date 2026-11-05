<div align="center">

# 🌲 Evergreen

### Your résumé, always in season.

Push code, change jobs, learn things, and stop rewriting your CV by hand.

[![tests](https://img.shields.io/github/actions/workflow/status/flushloll/evergreen/test.yml?branch=main&style=flat-square&label=tests)](https://github.com/flushloll/evergreen/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![JSON Resume](https://img.shields.io/badge/format-JSON_Resume-1f7a4d?style=flat-square)](https://jsonresume.org/schema)
[![MIT license](https://img.shields.io/badge/license-MIT-f4c430?style=flat-square)](LICENSE)

[Quick start](#quick-start) · [How it works](#how-it-works) · [What it grabs](#what-it-grabs) · [AI bullets](#ai-bullets-optional) · [FAQ](#faq)

<code>pip install git+https://github.com/flushloll/evergreen</code>

<br /><br />

<img src="docs/example.png" alt="A résumé rendered by Evergreen" width="720" />

</div>

---

I kept forgetting to add new projects to my résumé, so I made this. Evergreen keeps your résumé in one `resume.yaml` file. Every week it checks GitHub (and LinkedIn, if you want) for new stuff, adds it, and sends you a pull request. You look it over, fix the wording if you feel like it, and merge. You also get a PDF out of it.

## Quick start

```bash
pip install git+https://github.com/flushloll/evergreen
evergreen init --github <your-username>
evergreen sync      # pulls your GitHub stuff into resume.yaml
evergreen render    # makes dist/resume.pdf (+ .html and .md)
```

Then push the folder to a GitHub repo and turn on **Settings → Actions → General → Allow GitHub Actions to create pull requests**. That's it. A PR shows up on Mondays when there's something new, or you can kick one off from the Actions tab.

> [!TIP]
> **Want LinkedIn too?** LinkedIn doesn't have a public API, so instead of scraping, Evergreen reads the export LinkedIn will email you (**Settings → Data privacy → Get a copy of your data**):
> ```bash
> evergreen import-linkedin ~/Downloads/Basic_LinkedInDataExport.zip
> ```
> It only keeps the 5 files it needs. Your messages and connections stay out of the repo.

## How it works

```text
GitHub ─────┐
            ├──> evergreen sync ──> resume.yaml ──> evergreen render ──> pdf · html · md
LinkedIn ───┘                       (you edit this)
```

It plays nice with your edits:

- It only fills in blanks. Anything you wrote stays exactly as is.
- If you delete something it added, it won't come back.
- Want to see what it would change first? Run `evergreen sync --dry-run`.

## What it grabs

| From | Goes into |
| --- | --- |
| Your GitHub profile | Name, website, location, bio |
| Your repos | Projects: your most recent (or most starred) ones that have a description, tagged with languages and topics |
| PRs merged into other people's repos | An "Open-source contributions" project |
| Languages you code in | A "Languages" skills list |
| LinkedIn export | Jobs, education, skills, certifications |

You can tweak all of it in `evergreen.yml`, e.g. how many projects to show or which repos to skip.

## AI bullets (optional)

New projects come in with just a one-line description. If you set `ai.enabled: true` and add an `ANTHROPIC_API_KEY` secret, Claude reads each new repo's README and writes a few bullet points for it. It's told not to make anything up, and it never touches bullets you already have.

```bash
pip install "evergreen-cv[ai] @ git+https://github.com/flushloll/evergreen"
ANTHROPIC_API_KEY=sk-... evergreen sync --ai
```

## FAQ

**Will it mess up what I wrote?** No. It only adds. The one exception is the "Open-source contributions" entry, which it rewrites every time.

**Can I use a different look?** Yes. `resume.yaml` is standard [JSON Resume](https://jsonresume.org/themes), so any theme works.

**How does the PDF get made?** It prints the HTML with Chrome. GitHub's runners already have Chrome. On your laptop it uses Chrome if you have it and skips the PDF if you don't.

**Do I need a token?** Not for public repos.

## License

[MIT](LICENSE). Do whatever you want with it.
