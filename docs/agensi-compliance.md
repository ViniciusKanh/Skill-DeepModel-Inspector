# Agensi compliance checklist (v1.0.0)

Sources read on 2026-11-09: agensi.io/docs/packaging, /docs/security, /docs/submit-on-the-website.
Automated by `python tools/package_agensi.py` (results in `dist/package-report.json`). This is a self-check;
it does **not** mean the package was approved by Agensi.

| Requirement (Agensi docs) | Status | Evidence |
|---|---|---|
| One ZIP, one `SKILL.md` → single skill | OK | `dist/deepmodel-inspector-v1.0.0.zip`, 13 files, single top-level folder `deepmodel-inspector/` |
| `SKILL.md` starts with frontmatter; `name` and `description` present | OK | checked by `package_agensi.py`; optional `summary`, `version`, `tags`, `keywords`, `use_cases` included |
| Optional folders `scripts/`, `references/`, `templates/` | OK | present |
| No blocked executables (exe, dll, so, bin, wasm, jar…) | OK | only `.md` and `.py`; static check = 0 problems |
| No bundled dependencies / virtualenvs / caches | OK | none; scripts use the standard library only |
| Scripts run on their own from a temporary file | OK | each script copied alone to an empty temp dir and run with `python -I` from the extracted ZIP (12 runs, all expected exit codes) |
| Embedded data in scripts | OK | rule texts, stopword lists and patterns are embedded; no script reads other package files |
| Logic < 20 KB per script (guideline) | PARTIAL | see table below |
| ZIP ≤ 50 MB, ≤ 1,000 files; agent upload ≤ 100 files / 5 MB text | OK | 85,069 bytes, 13 text files |
| Security scan topics: dangerous commands, secrets, environment harvesting, network access, obfuscation, prompt injection | OK (self-check) | no `subprocess`, `os.system`, `eval`/`exec`, sockets/urllib/requests, `pickle`, `os.environ`/`getenv`, deletes or `shell=True` in scripts; no key-like strings; injection-detection patterns are readable lists with comments; SKILL.md contains only operating instructions |
| Name ≤ 60 chars, summary ≤ 300 chars | OK | 19 / 218 chars |
| No links to outside checkouts | OK | listing contains none |

## Script sizes (bytes)

| Script | File | Logic (no comments/docstrings) | Code without message text |
|---|---|---|---|
| dmi_checkpoint.py | 12,835 | 9,346 | 8,003 |
| dmi_compare.py | 24,174 | 19,150 | 16,162 |
| dmi_dataset.py | 33,276 | 25,775 | 22,029 |
| dmi_generation.py | 27,901 | 21,150 | 17,570 |
| dmi_investigate.py | 24,314 | 19,396 | 13,580 |
| dmi_leakage.py | 25,296 | 19,248 | 16,890 |
| dmi_report.py | 14,249 | 11,411 | 8,907 |
| dmi_tokenizer.py | 24,079 | 18,580 | 15,754 |
| dmi_training.py | 32,972 | 24,777 | 19,489 |

`dmi_dataset.py`, `dmi_training.py` and `dmi_generation.py` exceed the 20 KB guideline when explanation strings are
counted; only `dmi_dataset.py` exceeds it without them (22 KB). Agensi states this is a guideline and that embedded data
does not count. Possible follow-up if reviewers ask: split near-duplicate search out of `dmi_dataset.py`.

## Permissions a buyer should expect

- Runs `python3` scripts locally (terminal access).
- Reads the files the user names; writes JSON/Markdown/HTML results to a folder the user chooses (default prints to stdout).
- No network access, no credentials, no environment variables.
