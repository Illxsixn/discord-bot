"""
Zombie-GIFs über Agnes-API — einmalig generieren, lokal cachen (kein Live-Render im Kampf).
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image

from config import Config
from utils.agnes_images import AgnesImageError, agnes_configured, request_agnes_image
from utils.zombie_content import ZOMBIES, ZOMBIE_TYPE_BOSS, ZOMBIE_TYPE_RASENDER, ZOMBIE_TYPE_STREUNER

logger = logging.getLogger(__name__)

# Ordner → Prompt-Quelle (interne Typ-Schlüssel nur für Prompt-Traits)
ASSET_GENERATION_JOBS: tuple[tuple[str, str], ...] = (
    ("common", ZOMBIE_TYPE_STREUNER),
    ("fast", ZOMBIE_TYPE_RASENDER),
    ("boss", ZOMBIE_TYPE_BOSS),
)

FRAME_MOTION_HINTS: tuple[str, ...] = (
    "animation frame A, idle walk cycle",
    "animation frame B, idle walk cycle",
    "animation frame C, idle walk cycle",
    "animation frame D, idle walk cycle",
)

VARIANT_SCENE_HINTS: tuple[str, ...] = (
    "soft dark grey gradient background",
    "soft dark teal gradient background",
)

STYLE_SUFFIX = (
    "stylized fantasy game character sprite, semi-realistic digital illustration, "
    "muted colors, clean composition, full body centered, "
    "no blood, no gore, no text, no watermark, no real people, "
    "original fictional creature design"
)


def zombie_gif_path(folder: str, variant: int = 1) -> Path:
    """Pfad für ein gecachtes Zombie-GIF (generisch pro Ordner)."""
    filename = f"{folder}_v{Config.ZOMBIE_ASSET_PROMPT_VERSION}.gif"
    if variant > 1:
        filename = f"{folder}_{variant:02d}_v{Config.ZOMBIE_ASSET_PROMPT_VERSION}.gif"
    return Config.ZOMBIE_ASSETS_DIR / folder / filename


def build_zombie_frame_prompt(
    zombie_key: str,
    *,
    variant: int,
    frame: int,
) -> str:
    """Prompt für ein Animations-Frame."""
    zombie = ZOMBIES[zombie_key]
    traits = ", ".join(zombie.traits)
    motion = FRAME_MOTION_HINTS[frame % len(FRAME_MOTION_HINTS)]
    scene = VARIANT_SCENE_HINTS[variant % len(VARIANT_SCENE_HINTS)]

    if zombie.is_boss:
        return (
            f"Large stylized fantasy boss monster, {traits}, "
            f"{motion}, dramatic lighting, {scene}, low-angle shot, {STYLE_SUFFIX}"
        )

    if zombie_key == ZOMBIE_TYPE_RASENDER:
        return (
            f"Stylized fast fantasy enemy creature, {traits}, {motion}, "
            f"motion blur, slim build, red glowing eyes, {scene}, {STYLE_SUFFIX}"
        )

    return (
        f"Stylized slow fantasy enemy creature, {traits}, {motion}, "
        f"grey-green skin, worn clothes, {scene}, {STYLE_SUFFIX}"
    )


def _resize_frame(image: Image.Image) -> Image.Image:
    """Verkleinert Frames für Discord-kompatible GIF-Größe."""
    size = Config.ZOMBIE_GIF_OUTPUT_SIZE
    rgba = image.convert("RGBA")
    rgba.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (18, 18, 22, 255))
    offset = ((size - rgba.width) // 2, (size - rgba.height) // 2)
    canvas.paste(rgba, offset, rgba)
    return canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)


def _save_gif(frames: list[Image.Image], path: Path) -> None:
    """Speichert Frame-Liste als Loop-GIF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not frames:
        raise AgnesImageError("Keine Frames zum Speichern.")

    processed = [_resize_frame(frame) for frame in frames]
    duration_ms = Config.ZOMBIE_GIF_FRAME_MS
    processed[0].save(
        path,
        save_all=True,
        append_images=processed[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )


async def generate_zombie_gif_for_folder(
    folder: str,
    zombie_key: str,
    *,
    variant: int = 1,
    force: bool = False,
) -> Path:
    """Generiert ein GIF für einen Asset-Ordner (common/fast/boss)."""
    path = zombie_gif_path(folder, variant)

    if path.is_file() and not force:
        return path

    frames: list[Image.Image] = []
    for frame_idx in range(Config.ZOMBIE_GIF_FRAME_COUNT):
        prompt = build_zombie_frame_prompt(zombie_key, variant=variant - 1, frame=frame_idx)
        logger.info("Generiere Frame %s/%s: %s", frame_idx + 1, Config.ZOMBIE_GIF_FRAME_COUNT, path.name)
        try:
            png_bytes = await request_agnes_image(prompt)
        except AgnesImageError:
            fallback = (
                f"Stylized cute-fantasy game monster sprite, neutral pose, "
                f"walk cycle frame {frame_idx + 1}, plain dark gradient background, "
                "no text, no watermark, original character design"
            )
            logger.warning("Prompt abgelehnt — Fallback für Frame %s", frame_idx + 1)
            png_bytes = await request_agnes_image(fallback)
        with Image.open(BytesIO(png_bytes)) as img:
            frames.append(img.copy())

    _save_gif(frames, path)
    logger.info("Zombie-GIF gespeichert: %s (%d bytes)", path, path.stat().st_size)
    return path


async def ensure_zombie_asset_library(*, force: bool = False) -> list[Path]:
    """Generiert je Ordner mindestens ein GIF (common, fast, boss)."""
    if not agnes_configured():
        raise AgnesImageError("AGNES_API_KEY fehlt — Zombie-GIFs können nicht generiert werden.")

    created: list[Path] = []
    variant_counts = {
        "common": Config.ZOMBIE_GIF_VARIANTS_COMMON,
        "fast": Config.ZOMBIE_GIF_VARIANTS_FAST,
        "boss": 1,
    }

    for folder, zombie_key in ASSET_GENERATION_JOBS:
        count = variant_counts.get(folder, 1)
        for variant in range(1, count + 1):
            created.append(
                await generate_zombie_gif_for_folder(
                    folder,
                    zombie_key,
                    variant=variant,
                    force=force,
                )
            )
    return created


def list_cached_zombie_gifs() -> list[Path]:
    """Alle lokalen Zombie-GIFs."""
    root = Config.ZOMBIE_ASSETS_DIR
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.gif") if p.is_file())
