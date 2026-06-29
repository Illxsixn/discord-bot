"""
Generierung und Fortschritt täglicher Aufgaben.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from config import Config
from database.models import (
    PET_CHALLENGE_TYPES,
    ChallengeTask,
    ChallengeType,
    DailyChallengeRecord,
    is_pet_challenge_type,
)


def today_utc() -> str:
    """Heutiges Datum (UTC) als ISO-String."""
    return datetime.now(timezone.utc).date().isoformat()


def _random_message_target() -> int:
    return random.choice(Config.CHALLENGE_MESSAGE_TARGETS)


def _random_player_reward() -> int:
    return random.randint(Config.CHALLENGE_XP_MIN, Config.CHALLENGE_XP_MAX)


def _random_pet_reward() -> int:
    return random.randint(Config.CHALLENGE_PET_XP_MIN, Config.CHALLENGE_PET_XP_MAX)


def _pet_task_target(challenge_type: ChallengeType) -> int:
    if challenge_type == ChallengeType.PET_PLAY:
        return random.choice((1, 2, 3))
    if challenge_type == ChallengeType.PET_INFO:
        return 1
    return random.choice((2, 3, 5))


def _build_task(challenge_type: ChallengeType, *, key: str | None = None) -> ChallengeTask:
    """Erstellt eine einzelne Zufallsaufgabe."""
    task_key = key or challenge_type.value
    reward = _random_player_reward()
    if challenge_type == ChallengeType.MESSAGES:
        return ChallengeTask(type=challenge_type, key=task_key, target=_random_message_target(), reward_xp=reward)
    if challenge_type == ChallengeType.ACTIVE:
        return ChallengeTask(type=challenge_type, key=task_key, target=1, reward_xp=reward)
    if challenge_type == ChallengeType.REACTIONS:
        return ChallengeTask(
            type=challenge_type,
            key=task_key,
            target=random.choice((5, 10, 15, 20)),
            reward_xp=reward,
        )
    if is_pet_challenge_type(challenge_type):
        return ChallengeTask(
            type=challenge_type,
            key=task_key,
            target=_pet_task_target(challenge_type),
            reward_xp=0,
            reward_pet_xp=_random_pet_reward(),
        )
    return ChallengeTask(type=challenge_type, key=task_key, target=random.choice((3, 5, 7)), reward_xp=reward)


def _build_pet_task(*, key: str) -> ChallengeTask:
    """Erzeugt eine zufällige Pet-Tagesaufgabe."""
    challenge_type = random.choice(tuple(PET_CHALLENGE_TYPES))
    return _build_task(challenge_type, key=key)


def generate_daily_challenges(guild_id: int, user_id: int) -> DailyChallengeRecord:
    """Erzeugt tägliche Aufgaben (Level-XP + Pet-Aufgaben)."""
    pet_tasks = [_build_pet_task(key=f"pet_{index}") for index in range(1, Config.DAILY_PET_CHALLENGE_COUNT + 1)]
    level_count = Config.DAILY_CHALLENGE_COUNT - Config.DAILY_PET_CHALLENGE_COUNT
    pool = [ch_type for ch_type in ChallengeType if not is_pet_challenge_type(ch_type)]
    random.shuffle(pool)
    tasks = [_build_task(ch_type) for ch_type in pool[:level_count]]
    tasks.extend(pet_tasks)
    random.shuffle(tasks)
    return DailyChallengeRecord(
        guild_id=guild_id,
        user_id=user_id,
        challenge_date=today_utc(),
        challenges=tasks,
        generation_version=Config.CHALLENGE_GENERATION_VERSION,
    )


def _valid_player_reward(reward_xp: int) -> bool:
    return Config.CHALLENGE_XP_MIN <= reward_xp <= Config.CHALLENGE_XP_MAX


def _valid_pet_reward(reward_pet_xp: int) -> bool:
    return Config.CHALLENGE_PET_XP_MIN <= reward_pet_xp <= Config.CHALLENGE_PET_XP_MAX


def _merge_challenge_progress(
    previous: DailyChallengeRecord,
    generated: DailyChallengeRecord,
) -> DailyChallengeRecord:
    """Übernimmt Fortschritt aus älteren Tagesaufgaben."""
    previous_by_key = {task.key: task for task in previous.challenges}
    for task in generated.challenges:
        old_task = previous_by_key.get(task.key)
        if old_task is None:
            continue
        task.progress = min(task.target, old_task.progress)
        task.completed = old_task.completed
        if old_task.completed:
            task.reward_xp = old_task.reward_xp
            task.reward_pet_xp = old_task.reward_pet_xp
    return generated


def normalize_daily_challenges(record: DailyChallengeRecord) -> tuple[bool, DailyChallengeRecord]:
    """
    Stellt sicher, dass gespeicherte Aufgaben zur aktuellen Version passen.

    Belohnungen werden beim Tagesreset pro Aufgabe festgelegt — nicht beim Abschluss.
    """
    pet_count = sum(1 for task in record.challenges if is_pet_challenge_type(task.type))
    needs_regeneration = (
        len(record.challenges) != Config.DAILY_CHALLENGE_COUNT
        or pet_count != Config.DAILY_PET_CHALLENGE_COUNT
    )
    if needs_regeneration:
        regenerated = generate_daily_challenges(record.guild_id, record.user_id)
        regenerated.challenge_date = record.challenge_date
        return True, _merge_challenge_progress(record, regenerated)

    version_changed = record.generation_version < Config.CHALLENGE_GENERATION_VERSION
    if version_changed:
        record.generation_version = Config.CHALLENGE_GENERATION_VERSION

    changed = version_changed
    for task in record.challenges:
        if task.completed:
            continue
        if version_changed or not _valid_player_reward(task.reward_xp):
            task.reward_xp = _random_player_reward()
            changed = True
        if is_pet_challenge_type(task.type) and (
            version_changed or not _valid_pet_reward(task.reward_pet_xp)
        ):
            task.reward_pet_xp = _random_pet_reward()
            changed = True

    return changed, record


def challenge_progress_text(task: ChallengeTask) -> str:
    """Fortschrittsanzeige für Embeds."""
    if task.completed:
        return "✅ Abgeschlossen"
    return f"`{min(task.progress, task.target)}/{task.target}`"


def format_challenge_task_line(index: int, task: ChallengeTask) -> str:
    """Formatiert eine Tagesaufgabe übersichtlich."""
    return (
        f"**{index}.** {task.label}\n"
        f"└ {challenge_progress_text(task)} · Belohnung: {task.reward_text}"
    )
