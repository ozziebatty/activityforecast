"""Loads the YAML config that drives locations and activity scoring."""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent / "config"


def load_locations() -> list[dict]:
    with open(CONFIG_DIR / "locations.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_activities() -> dict:
    with open(CONFIG_DIR / "activities.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
