#!/usr/bin/env python3
"""Copy unique third-party license files from .venv into licenses/."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "licenses"
INDEX = ROOT / "Licenses.md"
LICENSE_NAME = re.compile(r"(license|licence|copying|copyright|notice)", re.I)
DIST = re.compile(r"^(.*)-(\d[^/]*)\.dist-info$")
KIND_CHECKS = [
    ("MIT", r"\bMIT License\b|Permission is hereby granted, free of charge"),
    ("Apache-2.0", r"Apache License"),
    ("BSD-3-Clause", r"Redistribution and use in source and binary forms"),
    ("BSD-2-Clause", r"BSD 2-Clause"),
    ("GPL-3.0", r"GNU GENERAL PUBLIC LICENSE.*Version 3"),
    ("GPL-2.0", r"GNU GENERAL PUBLIC LICENSE.*Version 2"),
    ("LGPL", r"Lesser General Public License|LGPL"),
    ("MPL-2.0", r"Mozilla Public License"),
    ("ISC", r"\bISC License\b"),
    ("PSF", r"Python Software Foundation"),
    ("Unlicense", r"This is free and unencumbered software"),
]


def site_packages() -> Path:
    matches = sorted((ROOT / ".venv").glob("lib/python*/site-packages"))
    if not matches:
        raise SystemExit("No .venv site-packages found. Run ./scripts/setup.sh first.")
    return matches[-1]


def is_license(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() in {".py", ".pyc", ".so", ".dylib"}:
        return False
    if path.stat().st_size > 2_000_000:
        return False
    return bool(LICENSE_NAME.search(path.name))


def dest_name(src: Path) -> str:
    if src.suffix.lower() == ".md":
        return src.stem + ".txt"
    if src.suffix == "":
        return src.name + ".txt"
    return src.name


def guess_kind(text: str) -> str:
    head = text[:4000]
    for label, pat in KIND_CHECKS:
        if re.search(pat, head, re.I | re.S):
            return label
    return "see file"


def copy_licenses() -> dict[str, set[str]]:
    site = site_packages()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    kinds: dict[str, set[str]] = {}

    for dist in sorted(site.glob("*.dist-info")):
        match = DIST.match(dist.name)
        pkg = match.group(1) if match else dist.name.replace(".dist-info", "")
        pkg_dir = OUT / pkg
        for src in dist.rglob("*"):
            if not is_license(src):
                continue
            parts = list(src.relative_to(dist).parts)
            if parts and parts[0].lower() in {"licenses", "license"}:
                parts = parts[1:] or [src.name]
            dest = pkg_dir.joinpath(*parts[:-1], dest_name(Path(parts[-1])))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            kinds.setdefault(pkg, set()).add(guess_kind(dest.read_text(encoding="utf-8", errors="replace")))

    notes = site / "licensing" / "license_notes.md"
    if notes.exists():
        dest = OUT / "soundfile-licensing" / "license_notes.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(notes.read_bytes())
        kinds.setdefault("soundfile-licensing", set()).add("BSD-3-Clause / mixed")
    return kinds


def write_index(kinds: dict[str, set[str]]) -> None:
    lines = [
        "# Licenses",
        "",
        "Third-party license texts used by Marvin, collected into `licenses/`.",
        "Original copies stay inside the Python packages.",
        "",
    ]
    for pkg in sorted(kinds, key=str.lower):
        labels = sorted(kinds[pkg])
        kind = labels[0] if len(labels) == 1 else "mixed"
        lines.append(f"- **{pkg}** — {kind}")
    lines.extend(["", "[[Marvin]]", ""])
    INDEX.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    kinds = copy_licenses()
    write_index(kinds)
    files = sum(1 for p in OUT.rglob("*") if p.is_file())
    print(f"packages={len(kinds)} files={files} index={INDEX}")


if __name__ == "__main__":
    main()
