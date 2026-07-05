"""Tests für Zombie-GIF-Assets und Embed-Persistenz."""

from __future__ import annotations

import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import discord
import pytest

from config import Config
from database.models import ZombieRunRecord, ZombieRunStatus
from utils.zombie_assets import (
    FALLBACK_GIFS,
    apply_zombie_visual,
    ensure_run_combat_image,
    has_local_zombie_gif,
    pick_zombie_visual_url,
)
from utils.zombie_content import ZOMBIE_TYPE_STREUNER


def _run(**kwargs) -> ZombieRunRecord:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1,
        guild_id=1,
        user_id=2,
        status=ZombieRunStatus.ACTIVE.value,
        wave=1,
        max_waves=3,
        player_hp=100,
        player_max_hp=100,
        current_zombie_key=ZOMBIE_TYPE_STREUNER,
        current_zombie_hp=40,
        created_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    return ZombieRunRecord(**defaults)


@pytest.fixture
def zombie_assets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isoliertes Asset-Verzeichnis für lokale GIF-Tests."""
    root = tmp_path / "zombies"
    for folder in ("common", "fast", "boss"):
        (root / folder).mkdir(parents=True)
    monkeypatch.setattr(Config, "ZOMBIE_ASSETS_DIR", root)
    return root


def test_fallback_gif_urls_are_reachable() -> None:
    for folder, urls in FALLBACK_GIFS.items():
        for url in urls:
            request = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.status == 200, f"{folder}: {url}"


def test_ensure_run_combat_image_is_stable_per_zombie() -> None:
    run = _run()
    first = ensure_run_combat_image(run, ZOMBIE_TYPE_STREUNER)
    second = ensure_run_combat_image(run, ZOMBIE_TYPE_STREUNER)
    assert first == second
    assert run.current_zombie_image_url == first


def test_apply_zombie_visual_keeps_image_on_melee_update() -> None:
    run = _run(current_zombie_image_url="https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif")
    embed = discord.Embed(title="Kampf")
    apply_zombie_visual(
        embed,
        run,
        ZOMBIE_TYPE_STREUNER,
        refresh_visual=False,
    )
    assert embed.image.url == run.current_zombie_image_url


def test_apply_zombie_visual_refreshes_on_new_zombie(zombie_assets_dir: Path) -> None:
    run = _run(current_zombie_image_url="https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif")
    embed = discord.Embed(title="Kampf")
    apply_zombie_visual(
        embed,
        run,
        ZOMBIE_TYPE_STREUNER,
        refresh_visual=True,
        use_attachment=False,
    )
    assert embed.image.url
    assert embed.image.url.startswith("https://")


def test_pick_zombie_visual_url_returns_http_without_local_assets(zombie_assets_dir: Path) -> None:
    url = pick_zombie_visual_url(ZOMBIE_TYPE_STREUNER)
    assert url.startswith("https://")


def test_local_agnes_gif_uses_attachment(zombie_assets_dir: Path) -> None:
    gif_path = zombie_assets_dir / "common" / "streuner_v2.gif"
    gif_path.write_bytes(b"GIF89a" + b"\x00" * 32)

    assert has_local_zombie_gif(ZOMBIE_TYPE_STREUNER)
    assert pick_zombie_visual_url(ZOMBIE_TYPE_STREUNER) == ""

    run = _run()
    embed = discord.Embed(title="Kampf")
    file = apply_zombie_visual(
        embed,
        run,
        ZOMBIE_TYPE_STREUNER,
        refresh_visual=True,
        use_attachment=True,
    )
    assert file is not None
    assert file.filename == "streuner_v2.gif"
    assert embed.image.url == "attachment://streuner_v2.gif"
    assert run.current_zombie_image_url == ""
