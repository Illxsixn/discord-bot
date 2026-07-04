"""Stellt sicher, dass Embeds zentral gebaut werden (keine Post-hoc-Mutation)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Erlaubte Dateien für Low-Level-Embed-Bausteine
ALLOWED_MUTATION_FILES = {
    ROOT / "utils" / "embeds.py",
    ROOT / "utils" / "zombie_assets.py",
    ROOT / "utils" / "pet_embeds.py",
    ROOT / "cogs" / "help.py",
}

FORBIDDEN_PATTERNS = (
    ".set_thumbnail(",
    ".set_footer(",
    ".add_field(",
    "discord.Embed(",
)


def _py_files() -> list[Path]:
    paths: list[Path] = []
    for folder in ("cogs", "utils"):
        paths.extend((ROOT / folder).rglob("*.py"))
    return paths


def test_no_post_hoc_embed_mutation_outside_helpers() -> None:
    violations: list[str] = []
    for path in _py_files():
        if path in ALLOWED_MUTATION_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                violations.append(f"{rel}: contains {pattern!r}")
    assert not violations, "Post-hoc embed mutation found:\n" + "\n".join(violations)


def test_embed_helpers_expose_footer_prefix() -> None:
    from utils import embeds

    assert "footer_prefix" in embeds.artwork_embed.__code__.co_varnames
    assert "footer_prefix" in embeds.info_embed.__code__.co_varnames
    assert "footer_prefix" in embeds.success_embed.__code__.co_varnames
    assert "author_name" in embeds.artwork_embed.__code__.co_varnames
