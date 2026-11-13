from __future__ import annotations

from pathlib import Path


def load_urls(path: Path) -> list[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            urls.append(stripped)
    return urls


def load_context(path: Path) -> str:
    """The global context document: free-form prose shared by every URL.

    Not per-site — the same instructions/field requirements apply to all sites
    in urls.txt; the skill-builder figures out, per site, how to satisfy them.
    """
    return path.read_text(encoding="utf-8").strip()
