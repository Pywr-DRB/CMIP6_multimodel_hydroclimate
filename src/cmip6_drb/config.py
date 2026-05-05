"""YAML config loader for cmip6_drb.

The config is intentionally a thin dataclass-ish wrapper over a dict so
collaborators can edit config.yaml without learning pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .paths import Paths, REPO_ROOT


@dataclass
class Config:
    raw: dict[str, Any]
    paths: Paths

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        with open(path) as f:
            raw = yaml.safe_load(f)
        paths = Paths(raw["paths"])
        return cls(raw=raw, paths=paths)

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)


def default_config_path() -> Path:
    return REPO_ROOT / "config.yaml"
