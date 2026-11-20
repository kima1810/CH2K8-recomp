# CHRB2K Launcher - Style Guide

Dark theme, gold and leather accents taken straight from the two logos.
All values live in `launcher.css` as CSS variables. Use the variables, never raw hex, in new code.

## Logos

| File | Use | Rules |
| --- | --- | --- |
| `assets/RSN.png` | Top-left of the sidebar (52 px) and the small footer mark (22 px) | Never stretch or recolor. Keep 12 px clear space. |
| `assets/CHRB2K.png` | Hero on the Play tab (168 px) | Sits on the dark background with the gold glow shadow. |

Both are circular with transparent corners, so they work on any dark surface. Do not place them on gold fills.

## Color

### Surfaces
| Token | Hex | Use |
| --- | --- | --- |
| `--bg` | `#0b0a09` | App background |
| `--surface-1` | `#14110d` | Sidebar, cards (bottom) |
| `--surface-2` | `#1c1710` | Cards (top), table header, hover |
| `--surface-3` | `#261f15` | Chips, switches, kbd |
| `--line` / `--line-soft` | `#3a2e1b` / `#2a2216` | Borders / dividers |

### Gold (from the logo rings)
| Token | Hex | Use |
| --- | --- | --- |
| `--gold-300` | `#e8c668` | Active text, focus ring, highlights |
| `--gold-400` | `#d4a63a` | Section labels, active markers |
| `--gold-500` | `#c8962e` | Gradient midpoint |
| `--gold-700` | `#8f5e12` | Hover borders, checked switch |
| `--gold-gradient` | 300 -> 500 -> 700 | Play button, hero title accent |

### Leather (from the basketball)
`--leather-700 #3a1a0c`, `--leather-900 #1d0d06`. Used only as a faint wash at the bottom-left of the main area.

### Text and status
| Token | Hex | Use |
| --- | --- | --- |
| `--text` | `#f3ecde` | Body and headings |
| `--text-muted` | `#a89f8e` | Labels, descriptions |
| `--text-faint` | `#6f6757` | Hints, column headers |
| `--text-on-gold` | `#1a1206` | Text on gold fills |
| `--ok` / `--warn` / `--err` | `#6fc08a` / `#e0a23a` / `#d2574a` | Status only |

**Rule:** gold means "primary or selected". Use at most one gold-filled button per screen.

## Typography

- Display: Orbitron (fallbacks Rajdhani, Segoe UI). Page titles, hero, buttons, section labels, table headers. Uppercase with `letter-spacing` .04-.16em for small sizes.
- Body: Segoe UI. 14 px / 1.5.
- Mono: Cascadia Mono / Consolas for paths and file names.
- Orbitron is not bundled yet. Until a font file is added to `assets/`, the fallbacks apply. Add it with `@font-face` in `launcher.css` when wanted.

| Role | Size / weight |
| --- | --- |
| Hero title | 44 / 800 |
| Page title | 30 / 800 |
| Section label | 12 / 700, uppercase, `--gold-400` |
| Nav item | 15 / 600 |
| Body | 14 / 400 |
| Hint | 12.5 / 400, `--text-faint` |

## Layout

- Window: 232 px sidebar + main area + 44 px footer bar. Minimum 640 px tall.
- Main padding 48 px sides, 32 px top. Under 1000 px wide everything stacks to one column.
- Spacing scale: 4, 8, 12, 16, 24, 32, 48 (`--space-1` to `--space-7`).
- Radii: 8 inputs, 12 rows and nav, 18 cards, pill for buttons and chips.

### Sections (sidebar order)
1. **Play** - hero, Play, Launch without mods, status card
2. **Mods** - installed list, detail panel, add/drop
3. **Roster** - rosters and their saves combined
4. **Legacies** - saved legacy files
5. **Settings** - display and folders

A **Links** block sits at the bottom of the sidebar: Discord, Recomp repo, Recomp Studio. Links open in the browser (`target="_blank" rel="noopener noreferrer"`), muted by default, gold on hover.

Removed from the reference: Online, Music, Movies, Paint Tool, About text and donation links (WWE-specific or not needed).

## Components

- **Nav item:** muted by default. Selected = gold text, faint gold gradient, 3 px gold bar on the left.
- **Primary button (`.btn-primary`):** gold gradient, dark text, Orbitron uppercase. Only Play.
- **Secondary button (`.btn`):** surface-2 fill, hairline border, gold-700 border on hover.
- **Chip:** `.chip` neutral, `.chip-gold` highlight, `.chip-ok`, `.chip-warn`. Never use color alone to carry status; keep the text label.
- **Switch:** 42x24. Checked = gold-700 track with gold-300 knob.
- **Card:** gradient surface-2 to surface-1, 18 px radius, 24 px padding.
- **Status row:** label left, value or green check right, hairline divider.
- **Mods table:** On, Name, Type, Version, Author. Selected row has a gold left bar and a faint gold fill. Row click selects, switch click toggles.
- **Dropzone:** dashed border, turns gold while a folder is dragged over it.
- **Footer bar:** keyboard hints on the left, status message on the right. All launcher feedback goes here.

## Mod tab behavior

- Enabling or disabling only changes what loads on the next launch. Say so in the footer message.
- **Play** applies the enabled mods, prepares assets, then starts the game.
- **Launch without mods** starts with stock game files and does not apply any mod.
- A mod is a folder under `mods/<id>/` with a `README.md` and its output files. Type, version and author come from the folder when available, otherwise show `--`.
- Disabled is the default for newly added mods.

## Accessibility and motion

- Body text on `--bg` is well above 4.5:1. `--text-faint` is for hints only, never essential info.
- Every control has a visible gold focus ring. Tabs and switches are keyboard reachable. Keys `1`-`5` switch section, `Enter` plays.
- Panel transition is a 220 ms fade/rise and is disabled under `prefers-reduced-motion`.

## Files

```
Launcher page/
  launcher.css           tokens + components
  index.html             the launcher page (talks to host.py; shows demo data if opened as a file)
  host.py                local host: serves the page, saves settings, applies mods, starts the game
  launcher-example.html  redirects to index.html
  STYLE_GUIDE.md         this file
  assets/RSN.png
  assets/CHRB2K.png
```
