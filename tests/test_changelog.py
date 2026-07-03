"""Tests für Changelog-Anzeige."""

from __future__ import annotations

from utils.changelog import (
    MAX_RELEASES_IN_EMBED,
    _important_changes,
    build_changelog_embed,
    load_changelog,
)


def test_changelog_embed_shows_last_three_releases() -> None:
    data = load_changelog()
    embed = build_changelog_embed()
    shown_versions = data.releases[:MAX_RELEASES_IN_EMBED]
    for release in shown_versions:
        assert f"**v{release.version}**" in embed.description
    if len(data.releases) > MAX_RELEASES_IN_EMBED:
        hidden = data.releases[MAX_RELEASES_IN_EMBED]
        assert f"**v{hidden.version}**" not in embed.description


def test_important_changes_prioritizes_new_features() -> None:
    changes = (
        "Fix: kleiner Bug",
        "Neu: /zombies",
        "Balance: HP",
        "Neu: /shop",
        "Fix: anderer Bug",
        "Fix: dritter Bug",
    )
    picked = _important_changes(changes, limit=3)
    assert picked[0] == "Neu: /zombies"
    assert picked[1] == "Balance: HP"
    assert picked[2] == "Neu: /shop"
    assert all(not change.startswith("Fix:") for change in picked)
