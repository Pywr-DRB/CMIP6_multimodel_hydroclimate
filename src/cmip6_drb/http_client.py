"""Resumable HTTPS download against hydrosource2.ornl.gov.

Used by the smoke test, the bulk download driver, and the per-task workers
in the parallel aggregator. 4xx codes that won't be cured by retry (404 etc.)
raise PermanentHttpError immediately so callers can mark them as missing-in-
source. Other transient errors retry with exponential backoff.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)


PERMANENT_HTTP_STATUS = {400, 401, 403, 404, 405, 410, 451}


class PermanentHttpError(RuntimeError):
    """Raised when the server returns a status that won't be cured by retrying."""
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status}: {url}")
        self.status = status
        self.url = url


def _sha256_of_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk), b""):
            h.update(buf)
    return h.hexdigest()


def download(
    url: str,
    dest: Path,
    *,
    retries: int = 5,
    backoff: float = 2.0,
    chunk_size: int = 1 << 20,
    timeout: float = 60.0,
    overwrite: bool = False,
) -> Path:
    """Download a URL to `dest` with resumable Range requests.

    Returns the final path. Idempotent: if `dest` exists and `overwrite=False`,
    returns immediately. Raises PermanentHttpError immediately for 4xx that
    won't be cured by retry (404 etc.); retries on 5xx and connection errors.
    """
    dest = Path(dest)
    if dest.exists() and not overwrite:
        log.info("Already present, skipping: %s", dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            existing = tmp.stat().st_size if tmp.exists() else 0
            headers = {"Range": f"bytes={existing}-"} if existing else {}
            with requests.get(url, headers=headers, stream=True, timeout=timeout) as r:
                if r.status_code == 416:
                    # Range not satisfiable -> file already complete on disk
                    break
                if r.status_code in PERMANENT_HTTP_STATUS:
                    # Drop the .part — restarting won't help.
                    if tmp.exists():
                        tmp.unlink()
                    raise PermanentHttpError(r.status_code, url)
                r.raise_for_status()
                mode = "ab" if existing else "wb"
                with open(tmp, mode) as f:
                    for buf in r.iter_content(chunk_size=chunk_size):
                        if buf:
                            f.write(buf)
            tmp.rename(dest)
            log.info("Downloaded %s -> %s", url, dest)
            return dest
        except PermanentHttpError:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            sleep = backoff * (2 ** (attempt - 1))
            log.warning("HTTPS attempt %d/%d failed: %s; sleeping %.1fs", attempt, retries, e, sleep)
            time.sleep(sleep)

    if tmp.exists() and not dest.exists():
        # Partial; leave .part for a future resume.
        pass
    raise RuntimeError(f"download failed after {retries} attempts: {url}") from last_err


def head_size(url: str, timeout: float = 30.0) -> int | None:
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        if r.status_code != 200:
            return None
        cl = r.headers.get("Content-Length")
        return int(cl) if cl is not None else None
    except Exception:
        return None
