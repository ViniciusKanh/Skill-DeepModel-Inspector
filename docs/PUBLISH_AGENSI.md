# Publishing checklist (manual — nothing has been submitted)

1. **Review** `docs/LICENSE-COMMERCIAL-DRAFT.md` (with a lawyer) and decide the final license text.
2. **Windows check** (recommended before release), in PowerShell with Python 3.13:
   ```powershell
   cd "C:\dev\DeepModel Inspector"
   py -3.13 -m venv .venv; .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   python examples\generate_synthetic.py
   pytest -q
   python tools\package_agensi.py
   ```
   Record the result in `docs/validation-results.md`. The ZIP SHA-256 should match `dist/SHA256SUMS.txt`
   (the ZIP is built deterministically).
3. **Agent test**: in Claude Code (or Codex), install the skill folder `agensi/deepmodel-inspector` and ask
   "Why is my LLM repeating the same sentences?" pointing at `examples/demo_experiment`.
4. **Submit** at agensi.io/dashboard/submit:
   - ZIP: `dist/deepmodel-inspector-v1.0.0.zip`
   - Name, summary, description, categories, tags, FAQ, limitations: copy from `docs/agensi-listing.md`
   - "See it in action": the demo section of `docs/agensi-listing.md` (> 700 characters)
   - Compatibility note: "Python 3.11+ (standard library only), CPU, offline."
   - Price: US$ 29 one-time (requires a connected payout method)
   - Logo/screenshots: optional (e.g. screenshot of `examples/sample_reports/audit.html`)
5. Review the permissions detected by Agensi (terminal + file read/write) and submit. Approval is decided by Agensi's
   automated scan and human review.
6. Do not publish the GitHub repository until the license is final.
