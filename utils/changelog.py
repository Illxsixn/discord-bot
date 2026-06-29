"""
Changelog laden und als Embed darstellen.

Quelle: data/changelog.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import discord

from utils.embeds import apply_brand_footer, info_embed

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "data" / "changelog.json"
MAX_RELEASES_IN_EMBED = 5


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


def build_changelog_embed(*, max_releases: int = MAX_RELEASES_IN_EMBED) -> discord.Embed:
    """Erstellt ein übersichtliches Changelog-Embed."""
    data = load_changelog()
    sections: list[str] = []

    for release in data.releases[:max_releases]:
        bullets = "\n".join(f"• {change}" for change in release.changes)
        sections.append(f"**v{release.version}**\n{bullets}")

    description = "\n\n".join(sections) if sections else "Noch keine Einträge."
    embed = info_embed("📋 Changelog", description)
    apply_brand_footer(embed, prefix=f"Version {data.version}")
    return embed
