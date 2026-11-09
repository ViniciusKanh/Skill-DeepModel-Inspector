# UI Design System — "Retro AI Lab / CRT Gaming Terminal"

Reference material (approved prototypes and brand guide) lives in `design/references/`. The UI recreates the
look in CSS/React; no prototype screenshot is used as a background or component.

## Brand
- Official logo: `frontend/src/assets/brand/logo.png` (from `design/references/07-logo-official.png`, unaltered).
- Icon: monitor + brain + magnifier crop of the official logo (`logo-icon.png`), used in the sidebar and favicon.
- Mascot: pixel character cropped from the approved dashboard prototype (`mascot.png`), used in empty states and the
  root-cause summary only, rendered with `image-rendering: pixelated`.

## Tokens (`frontend/src/styles/index.css`, `tailwind.config.js`)
| Token | Hex | Use |
|---|---|---|
| Phosphor Green | `#39FF88` | primary, success, active nav, train series |
| Cyan | `#00E5FF` | interface highlights, info, focus ring, LR series |
| Purple | `#A255FF` | accent, secondary buttons, hypotheses |
| Amber | `#FFB000` | attention, bullets, warnings, perplexity |
| Navy | `#0B1839` | panels, modals |
| Console Black | `#1A1030` | app background family |
| Danger (pink) | `#FF4D8D` | critical/high, errors, val-loss series uses `#FF4DD8` |

Typography: **Press Start 2P** for titles, panel headers and buttons only; **IBM Plex Mono** for all data, tables,
forms and long text; **VT323** for terminal details (loader, version plaque). Pixel fonts are never used for long text.

## Components
- `.bezel` + `.screen`: CRT monitor frame around the main area; optional scanlines (`::after`).
- `Panel`: neon border by tone, amber square bullet, pixel title, hatch divider, optional actions.
- `StatCard`: icon + label + value (IBM Plex Mono 22px) + sub-line; values always come from engine output.
- Buttons `.btn` (primary/purple/amber/cyan/danger, `btn-sm`) with stepped "pixel" corners; hover glow, press offset, disabled state.
- Chips `.chip` for severity (CRITICAL/HIGH pink, MEDIUM amber, LOW cyan, INFO grey) and status (CONFIRMED green, POTENTIAL amber, INCONCLUSIVE grey).
- `JobProgress`: pixel progress bar; determinate only when the backend reports real steps, otherwise indeterminate scan animation.
- `Loader`: terminal prompt with blinking block cursor. `EmptyState`: mascot + guidance + actions.
- `Modal` (Esc to close, focus on open), `Toasts` (aria-live), `Hint` tooltips (title + aria-label).
- Charts (Recharts): dark grid, brand series colours, legend chips toggle series, Brush for range zoom, descriptive range table.

## Accessibility & comfort
- Visible focus ring (cyan), keyboard-operable tables/rows (Enter opens details), `aria-pressed`, `role=switch`, `role=status/alert`.
- Settings → CRT effects off (removes glow and scanlines) and Animations off; `prefers-reduced-motion` is honoured.
- Layout: sidebar collapses to icons below 1024 px; grids collapse to one column on phones; no horizontal page scroll
  (verified by Playwright at 1920×1080, 1440×900, 1366×768 and 390×844).
