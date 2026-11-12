# Windows installer & GitHub Releases

## What the user gets
- `DeepModelInspector-Setup-<version>.exe` — per-user install (no admin) in `%LOCALAPPDATA%\Programs\DeepModel Inspector`,
  Start-menu entry, optional desktop icon. Opening it starts the local API on `127.0.0.1` and opens the browser.
- `DeepModelInspector-<version>-portable-win64.zip` — same app, unzip and run `DeepModelInspector.exe`.
- `SHA256SUMS.txt`.

User data (projects, reports, Live models transcripts) lives in `%LOCALAPPDATA%\DeepModelInspector\workspace` and is
kept on uninstall. Default authorized roots: the bundled examples and the user's home folder (editable in Settings).

## Build locally (Windows)
Requirements: Python 3.11+, Node 18+, [Inno Setup 6](https://jrsoftware.org/isdl.php).
```powershell
powershell -ExecutionPolicy Bypass -File scripts\Build-Installer.ps1 -Version 1.0.0
# -> build\release\DeepModelInspector-Setup-1.0.0.exe (+ portable zip, SHA256SUMS.txt)
```
Without Inno Setup the script still produces the portable folder `build\pyinstaller\dist\DeepModelInspector`.

## Publish with GitHub Actions
`.github/workflows/release.yml` runs on `windows-latest` when a tag `v*` is pushed: tests → frontend build →
PyInstaller → Inno Setup → GitHub Release with the files above.
```powershell
git tag v1.0.0
git push origin v1.0.0
```
Notes:
- In a **private** repository, Releases are visible only to collaborators. For public downloads use a public repo
  (or a separate public "releases" repo) — decide before tagging.
- The executable is **not code-signed**: Windows SmartScreen shows "Unknown publisher" (More info → Run anyway).
  Signing requires a code-signing certificate (or the Microsoft Store/MSIX route in `deployment-architecture.md`).

## Other workflows
| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | push / PR / manual | ruff + pytest on Ubuntu and Windows (3.11, 3.13); frontend tsc, vitest, build |
| `release.yml` | tag `v*` / manual | builds Setup.exe + portable ZIP; publishes a Release on tags, artifact otherwise |
| `docs-media.yml` | push to `main` (app code) / manual | browser e2e tests, then `tools/capture_media.py`: screenshots, tour MP4 + GIF, README `MEDIA` block; commits as `github-actions[bot]` with `[skip ci]` |

Locally: `python tools/capture_media.py` (needs Playwright Chromium, a built frontend and ffmpeg for MP4/GIF).
Workflows need **Settings → Actions → General → Workflow permissions: Read and write** for the release and the media commit.

## Validation status
- PyInstaller onedir build validated on Linux (frozen app served UI, API, simulated models, workspace in user dir).
- The Windows build, Inno Setup step and the workflow have **not** been executed in the development sandbox; run
  `Build-Installer.ps1` or the workflow (`workflow_dispatch`) once to validate on Windows.
