"""One-time interactive Globus authorization.

Run on a login node where you can paste a URL into a browser:

    python scripts/00_globus_authorize.py --client-id <YOUR_NATIVE_APP_CLIENT_ID>

Writes a refresh token to the path configured in config.yaml
(default: ~/.globus_drb_refresh_token.json). Subsequent script runs read
this token and authenticate non-interactively.

Register a Native App at https://app.globus.org/settings/developers ->
"Register a thick client or script that will be installed and run by users
on their devices". Use any redirect URI listed by the SDK; the standard
out-of-band one works.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[1] / "src"))

from cmip6_drb import config as cfg_mod  # noqa: E402
from cmip6_drb.globus_client import authorize_interactive  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()))
    ap.add_argument("--client-id", help="Override globus.client_id from config")
    ap.add_argument("--token-path", help="Override globus.refresh_token_path from config")
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    client_id = args.client_id or cfg["globus"]["client_id"]
    if not client_id:
        ap.error("Provide --client-id or set globus.client_id in config.yaml")
    token_path = Path(args.token_path or cfg["globus"]["refresh_token_path"]).expanduser()

    authorize_interactive(client_id, token_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
