"""Tests für Changelog-Laden und Format-Richtlinien."""

from __future__ import annotations

from utils.changelog import (
    MAX_CHANGES_PER_RELEASE_IN_EMBED,
    MAX_RELEASES_IN_EMBED,
    load_changelog,
)


def test_load_changelog_has_current_version() -> None:
    data = load_changelog()
    assert data.version == data.releases[0].version


def test_embed_constants() -> None:
    assert MAX_RELEASES_IN_EMBED == 2
    assert MAX_CHANGES_PER_RELEASE_IN_EMBED == 5


def test_at_most_two_releases_selected_for_embed() -> None:
    data = load_changelog()
    shown = data.releases[:MAX_RELEASES_IN_EMBED]
    assert len(shown) <= 2


def test_releases_have_short_change_lists() -> None:
    """Jede Version sollte höchstens 5 Einträge haben (Richtlinie)."""
    data = load_changelog()
    for release in data.releases:
        assert len(release.changes) <= 5, f"v{release.version} hat zu viele Punkte"
