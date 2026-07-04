#!/usr/bin/env python3
"""
Löscht alle gecachten Pet-Portraits (z. B. nach Prompt-Version-Bump).

Neue Portraits werden beim nächsten /pet display automatisch generiert.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.pet_ai_images import clear_pet_portrait_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    removed = clear_pet_portrait_cache()
    logger.info("%d Pet-Portrait(s) gelöscht.", removed)


if __name__ == "__main__":
    main()
