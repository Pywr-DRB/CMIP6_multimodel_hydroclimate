"""Idempotent task state tracker — JSONL append-only log.

Used by both download_bulk and the MPI aggregator to skip work that's already
done after a kill/resume. Each line is one JSON object:
    {"sim": ..., "var": ..., "year": ..., "stage": "downloaded"|"aggregated"|"failed",
     "ts": "2026-05-04T20:00:00", "info": "..."}

The "completed set" for a given stage is the set of (sim, var, year) tuples
whose latest record at that stage is success.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterator


class StateLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def record(self, *, sim: str, var: str, year: int, stage: str, info: str = "") -> None:
        rec = {
            "sim": sim, "var": var, "year": int(year),
            "stage": stage,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "info": info,
        }
        line = json.dumps(rec)
        with self._lock, open(self.path, "a") as f:
            f.write(line + "\n")

    def iter_records(self) -> Iterator[dict]:
        if not self.path.exists():
            return iter(())
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def completed(self, stage: str) -> set[tuple[str, str, int]]:
        out: set[tuple[str, str, int]] = set()
        for r in self.iter_records():
            if r.get("stage") == stage:
                out.add((r["sim"], r["var"], int(r["year"])))
        return out
