# Obsidian format skills (vendored)

Source: https://github.com/kepano/obsidian-skills
Author: Steph Ango (@kepano)
License: MIT (see LICENSE in this directory)

Marvin vendors only the format skills for Phase 1:

- `obsidian-markdown`
- `obsidian-bases`
- `json-canvas`

## Phase 2 (not bundled)

These skills from the upstream repo are **not** enabled in Marvin yet:

- `obsidian-cli` — requires the Obsidian desktop app + official CLI; would duplicate Marvin’s native vault tools (`backend/tools/obsidian.py`)
- `defuddle` — requires a separate Defuddle CLI; overlaps Marvin’s web-search tooling

Do not enable CLI/Defuddle by default. Revisit only if FS vault tools hit limits that Obsidian’s indexed CLI can solve.
