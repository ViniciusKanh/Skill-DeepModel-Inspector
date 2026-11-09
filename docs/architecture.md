# Architecture

```
src/deepmodel_inspector/
  security/guard.py        path confinement, sensitive-file and unsafe-format refusal, size limits, output guard
  core/common.py           finding/result schema, descriptive statistics, CSV/JSON/JSONL/TXT loader, redaction
  parsers/records.py       record formats (text, instruction, messages, prompt/response, CSV field),
                           normalization, shingles, 13-gram hashes, seeded MinHash + LSH
  analyzers/
    training.py            TRN.* rules            dataset.py     DAT.* rules
    leakage.py             LEK.* rules            tokenizer.py   TOK.* rules
    generation.py          GEN.* rules            compare.py     CMP.* rules
    checkpoint.py          CKP.* rules (safetensors header / JSON only)
  diagnostics/
    inventory.py           artifact discovery + classification + audit orchestration
    rootcause.py           consolidation, global IDs (DMI-###), RC.* hypotheses, intents, answers
  reporting/render.py      Markdown and static HTML (escaped, inline SVG chart)
  cli.py                   `deepmodel` command (11 subcommands)
tools/build_skill.py       generates standalone skill scripts from the engine modules
tools/package_agensi.py    static checks, deterministic ZIP, isolated runs from the ZIP, SHA-256
agensi/deepmodel-inspector SKILL.md, scripts/, references/, templates/
```

## Data flow

1. **Input guard** — every path goes through `safe_input_path` (resolve, confine to roots, refuse secrets and
   pickle formats, enforce size). Files are only opened for reading.
2. **Parsing** — `load_table` returns records plus parse info (format, malformed lines, truncation).
3. **Analyzers** — pure functions `records → result` with `metrics`, `findings`, `limitations` (and `series` for
   charts). Each analyzer depends only on `core/common.py`, `parsers/records.py` and `security/guard.py`.
4. **Consolidation** — `rootcause.consolidate(results, question)` re-numbers findings globally, builds hypotheses,
   experiments, summary and the question answer.
5. **Rendering** — JSON (canonical), Markdown, HTML.

## Engine ↔ skill parity

The Agensi runtime executes each script alone from a temporary file, so scripts cannot import each other.
`tools/build_skill.py` concatenates exactly the modules a script needs, removes intra-package imports and dead code
(AST-based tree shaking from the script entry point) and adds a small argparse entry point. Because the analysis code
is the same source, engine and scripts produce identical JSON; `tests/test_skill_scripts.py` verifies this for every
analyzer and for the investigate/report stage, and checks that the committed scripts are up to date.

Large logic is split into independent stages that exchange explicit JSON files: analysis scripts →
`dmi_investigate.py` (consolidated JSON) → `dmi_report.py` (Markdown/HTML).

## Extending

Add a rule inside the relevant analyzer with `finding(rule=..., ...)`, document it in
`docs/diagnostic-methodology.md` / `references/rules.md`, add positive and negative tests, and (for cross-artifact
logic) an `RC.*` entry in `rootcause.hypotheses`. Run `python tools/build_skill.py` to regenerate the scripts.
