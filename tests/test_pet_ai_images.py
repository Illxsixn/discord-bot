"""Tests für Pet-Portrait-Prompts und Cache."""

from __future__ import annotations

from database.models import PetRecord
from utils.pet_ai_images import build_pet_portrait_prompt, clear_pet_portrait_cache, pet_portrait_path
from utils.pets import get_species_by_name


def _pet(**kwargs) -> PetRecord:
    defaults = dict(
        id=7,
        owner_id=1,
        guild_id=1,
        name="Testi",
        species="schleimfreund",
        evolution_stage="baby",
        level=1,
        xp=0,
        mood="focus",
        catchphrase="Hi",
        is_active=True,
    )
    defaults.update(kwargs)
    return PetRecord(**defaults)


def test_portrait_prompt_requests_single_face() -> None:
    pet = _pet()
    species = get_species_by_name(pet.species)
    prompt = build_pet_portrait_prompt(pet, species)
    assert "exactly one face" in prompt
    assert "no duplicate faces" in prompt
    assert "no twins" in prompt


def test_portrait_path_uses_config_version() -> None:
    path = pet_portrait_path(7, "baby")
    assert "_v" in path.name
    assert path.suffix == ".png"


def test_clear_pet_portrait_cache_on_empty_dir(tmp_path, monkeypatch) -> None:
    from config import Config

    monkeypatch.setattr(Config, "PET_IMAGE_DIR", tmp_path)
    assert clear_pet_portrait_cache() == 0
