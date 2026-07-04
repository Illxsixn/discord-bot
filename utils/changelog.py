"""
Changelog laden und als Embed darstellen.

Quelle: data/changelog.json

Richtlinie: Kurze Releases (max. 5 Punkte), häufige Patch-Versionen,
im Embed nur die 2 neuesten Versionen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from utils.embeds import info_embed, spaced_lines

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "data" / "changelog.json"
MAX_RELEASES_IN_EMBED = 2
MAX_CHANGES_PER_RELEASE_IN_EMBED = 5


@dataclass(frozen=True)
class ChangelogRelease:
    """Eine Version mit Kurzpunkten."""

    version: str
    changes: tuple[str, ...]


@dataclass(frozen=True)
class ChangelogData:
    """Aktuelle Bot-Version und Release-Historie."""

    version: str
    releases: tuple[ChangelogRelease, ...]


def load_changelog() -> ChangelogData:
    """Lädt den Changelog aus der JSON-Datei."""
    raw = json.loads(CHANGELOG_PATH.read_text(encoding="utf-8"))
    releases = tuple(
        ChangelogRelease(
            version=str(item["version"]),
            changes=tuple(str(change) for change in item["changes"]),
        )
        for item in raw.get("releases", [])
    )
    return ChangelogData(version=str(raw["version"]), releases=releases)


def _format_release_section(release: ChangelogRelease) -> str:
    """Formatiert eine Version mit begrenzter Punktzahl fürs Embed."""
    visible = release.changes[:MAX_CHANGES_PER_RELEASE_IN_EMBED]
    bullets = "\n".join(f"• {change}" for change in visible)
    remaining = len(release.changes) - len(visible)
    if remaining > 0:
        bullets += f"\n• … und {remaining} weitere"
    return f"**v{release.version}**\n{bullets}"


def build_changelog_embed(*, max_releases: int = MAX_RELEASES_IN_EMBED):
    """Erstellt ein kompaktes Changelog-Embed (max. 2 Versionen)."""
    data = load_changelog()
    shown = data.releases[:max_releases]
    sections = [_format_release_section(release) for release in shown]

    description = spaced_lines(*sections) if sections else "Noch keine Einträge."
    if len(data.releases) > max_releases:
        description += f"\n\n*Ältere Versionen: v{data.releases[-1].version} …*"

    return info_embed("📋 Changelog", description, footer_prefix=f"Version {data.version}")
