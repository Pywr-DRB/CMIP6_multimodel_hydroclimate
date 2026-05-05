"""Path resolution for cmip6_drb.

Resolves staging/intermediate/final/log directories from config and ensures
they exist. All paths returned are pathlib.Path objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve(p: str | Path, root: Path = REPO_ROOT) -> Path:
    p = Path(p).expanduser()
    return p if p.is_absolute() else (root / p).resolve()


class Paths:
    def __init__(self, cfg_paths: Mapping[str, str], root: Path = REPO_ROOT) -> None:
        self.repo_root = root
        self.shapefile = resolve(cfg_paths["shapefile"], root)
        self.staging_raw = resolve(cfg_paths["staging_raw"], root)
        self.staging_intermediate = resolve(cfg_paths["staging_intermediate"], root)
        self.final_parquet = resolve(cfg_paths["final_parquet"], root)
        self.final_weights = resolve(cfg_paths["final_weights"], root)
        self.state_file = resolve(cfg_paths["state_file"], root)
        self.log_dir = resolve(cfg_paths["log_dir"], root)

    def ensure(self) -> None:
        for p in (
            self.staging_raw,
            self.staging_raw / "permanent",
            self.staging_intermediate,
            self.final_parquet,
            self.final_weights,
            self.log_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def raw_dest(self, simulation: str, variable: str, filename: str, *, permanent: bool) -> Path:
        base = self.staging_raw / "permanent" if permanent else self.staging_raw
        return base / simulation / variable / filename

    def intermediate(self, simulation: str, variable: str, year: int) -> Path:
        return self.staging_intermediate / f"{simulation}__{variable}__{year}.parquet"

    def final(self, simulation: str, variable: str) -> Path:
        return self.final_parquet / f"{simulation}__{variable}.parquet"
