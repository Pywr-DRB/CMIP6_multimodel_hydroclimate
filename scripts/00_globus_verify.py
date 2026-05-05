"""Verify the Globus collection path layout against our manifest.

Run AFTER `scripts/00_globus_authorize.py` has produced a refresh token.
This script:
  1. Lists the configured `globus.source_root` and prints the top-level entries.
  2. Picks the Phase 1 smoke task (DaymetV4/prcp/1980 by default), and walks
     `{root}/{simulation}/{variable}/` to confirm the expected file is present.
  3. Reports back the size + last-modified so you can spot-check it matches the
     HydroSource HTTPS listing (~148 MB).

If step (2) fails because there's a wrapper directory inside the DOI archive
(e.g., `SWA9505V3/`), this script will detect it and print the corrected
`source_root` to paste into config.yaml.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[1] / "src"))

from cmip6_drb import config as cfg_mod, manifest  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("globus_verify")


def _make_client(cfg):
    import globus_sdk

    g = cfg["globus"]
    rt_path = Path(g["refresh_token_path"]).expanduser()
    if not rt_path.exists():
        log.error("Refresh token not found at %s. Run scripts/00_globus_authorize.py first.", rt_path)
        sys.exit(2)
    if not g.get("client_id"):
        log.error("globus.client_id is empty in config.yaml — set it to your Native App client ID.")
        sys.exit(2)

    tokens = json.loads(rt_path.read_text())
    rt = tokens["transfer.api.globus.org"]["refresh_token"]
    auth = globus_sdk.NativeAppAuthClient(g["client_id"])
    authorizer = globus_sdk.RefreshTokenAuthorizer(rt, auth)
    return globus_sdk.TransferClient(authorizer=authorizer)


def _ls(tc, ep, path):
    try:
        return list(tc.operation_ls(ep, path=path))
    except Exception as e:  # noqa: BLE001
        log.error("ls failed for %s:%s -> %s", ep, path, e)
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()))
    ap.add_argument("--simulation", default=None)
    ap.add_argument("--variable", default=None)
    ap.add_argument("--year", type=int, default=None)
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    g = cfg["globus"]
    ep = g["source_endpoint_uuid"]
    root = g["source_root"].rstrip("/") + "/"

    tc = _make_client(cfg)

    # Probe the destination first (cheaper, fails earlier if mapping is wrong).
    dest_ep = g.get("destination_endpoint_uuid")
    dest_root = g.get("destination_root")
    if dest_ep:
        log.info("Probing destination %s:%s", dest_ep, dest_root or "/")
        try:
            dest_listing = list(tc.operation_ls(dest_ep, path=dest_root or "/"))
            log.info("  destination OK; %d entries (sample: %s)",
                     len(dest_listing), [e["name"] for e in dest_listing[:5]])
        except Exception as e:  # noqa: BLE001
            log.warning("  destination ls failed: %s", e)
            log.warning("  (Continuing with source verification — destination may need permissions fix.)")

    log.info("Listing %s:%s", ep, root)
    top = _ls(tc, ep, root)
    if not top:
        log.error("Empty listing or auth failure. Check the UUID / path / scopes.")
        return 1
    names = [e["name"] for e in top]
    log.info("Top-level entries (%d): %s", len(names), names[:20])

    # Detect possible wrapper directory.
    expected = {"DaymetV4", "Livneh"}
    if expected & set(names):
        log.info("OK: top-level contains DaymetV4 / Livneh — manifest paths will resolve as-is.")
        new_root = None
    else:
        # Look one level deeper for the expected entries (common DOI-archive wrapper).
        candidate = None
        for e in top:
            if e["type"] != "dir":
                continue
            sub = _ls(tc, ep, root + e["name"] + "/")
            sub_names = {x["name"] for x in sub}
            if expected & sub_names:
                candidate = e["name"]
                break
        if candidate:
            new_root = root + candidate
            log.warning("Wrapper directory detected. Update config.yaml:")
            log.warning("  globus.source_root: \"%s\"", new_root.rstrip("/"))
        else:
            log.error("Could not find DaymetV4/Livneh anywhere within %s (one level deep).", root)
            return 1

    # Probe the smoke task (or whatever was overridden).
    s = cfg["smoke_test"]
    sim = args.simulation or s["simulation"]
    var = args.variable or s["variable"]
    yr = int(args.year or s["year"])
    task = manifest.Task(simulation=sim, variable=var, year=yr)

    probe_root = (new_root or root).rstrip("/") + "/"
    file_dir = probe_root + f"{sim}/{var}/"
    log.info("Listing %s:%s", ep, file_dir)
    var_listing = _ls(tc, ep, file_dir)
    fname = task.filename()
    match = next((x for x in var_listing if x["name"] == fname), None)
    if match:
        log.info("FOUND %s — size=%s last_modified=%s",
                 fname, match.get("size"), match.get("last_modified"))
        log.info("Globus access verified.")
        return 0
    else:
        sample = [x["name"] for x in var_listing[:5]]
        log.error("File %s NOT found in %s. Sample entries: %s", fname, file_dir, sample)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
