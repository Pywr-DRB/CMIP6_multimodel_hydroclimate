"""Globus SDK transfer wrapper.

Authenticates non-interactively using a refresh token persisted to disk
(produced once via the interactive `authorize()` flow). The refresh token
file is intentionally NOT a client-credentials JWT — it's a per-user OAuth
refresh token suitable for a single-developer setup. For shared accounts,
swap to ConfidentialAppAuthClient + ClientCredentialsAuthorizer.

This module is feature-gated by `globus.enable: true` in config.yaml. Until
the SWA9505V3 collection UUID is confirmed by ORNL, the smoke test should
run via http_client.py.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)


@dataclass
class GlobusConfig:
    client_id: str
    source_endpoint_uuid: str
    destination_endpoint_uuid: str
    refresh_token_path: Path


class GlobusTransferClient:
    """Thin wrapper over globus_sdk.TransferClient for batched submits + polling."""

    def __init__(self, cfg: GlobusConfig) -> None:
        # Imported lazily so that environments without globus-sdk can still
        # import the rest of cmip6_drb.
        import globus_sdk  # noqa: F401  (imported here for early failure)

        self.cfg = cfg
        self._tc = self._build_transfer_client()

    def _build_transfer_client(self):
        import globus_sdk

        rt_path = Path(self.cfg.refresh_token_path).expanduser()
        if not rt_path.exists():
            raise FileNotFoundError(
                f"Refresh token not found at {rt_path}. Run "
                "`python -m cmip6_drb.globus_client authorize` once interactively."
            )
        with open(rt_path) as f:
            tokens = json.load(f)

        auth_client = globus_sdk.NativeAppAuthClient(self.cfg.client_id)
        transfer_rt = tokens["transfer.api.globus.org"]["refresh_token"]
        authorizer = globus_sdk.RefreshTokenAuthorizer(transfer_rt, auth_client)
        return globus_sdk.TransferClient(authorizer=authorizer)

    def submit_batch(self, pairs: Iterable[tuple[str, str]], label: str) -> str:
        """Submit a transfer of (source_path, dest_path) pairs. Returns task_id."""
        import globus_sdk

        td = globus_sdk.TransferData(
            self._tc,
            self.cfg.source_endpoint_uuid,
            self.cfg.destination_endpoint_uuid,
            label=label,
            verify_checksum=True,
            sync_level="checksum",
        )
        for src, dst in pairs:
            td.add_item(src, dst)
        result = self._tc.submit_transfer(td)
        return result["task_id"]

    def wait(self, task_id: str, *, poll_seconds: float = 30.0, timeout_seconds: float | None = None) -> dict:
        start = time.time()
        while True:
            status = self._tc.get_task(task_id)
            if status["status"] in {"SUCCEEDED", "FAILED"}:
                return status.data
            if timeout_seconds is not None and time.time() - start > timeout_seconds:
                raise TimeoutError(f"Globus task {task_id} did not finish within {timeout_seconds}s")
            time.sleep(poll_seconds)


def authorize_interactive(client_id: str, refresh_token_path: Path) -> None:
    """Run the Native App device-code flow once to write a refresh token to disk.

    Invoke from a login node:
        python -c "from cmip6_drb.globus_client import authorize_interactive; \\
                   authorize_interactive('<CLIENT_ID>', '~/.globus_drb_refresh_token.json')"
    """
    import globus_sdk

    client = globus_sdk.NativeAppAuthClient(client_id)
    client.oauth2_start_flow(refresh_tokens=True, requested_scopes="urn:globus:auth:scope:transfer.api.globus.org:all")
    print("Open the URL in any browser, log in, then paste the resulting auth code:")
    print(client.oauth2_get_authorize_url())
    code = input("auth code> ").strip()
    response = client.oauth2_exchange_code_for_tokens(code)
    rt_path = Path(refresh_token_path).expanduser()
    rt_path.parent.mkdir(parents=True, exist_ok=True)
    rt_path.write_text(json.dumps(response.by_resource_server, indent=2))
    rt_path.chmod(0o600)
    print(f"Refresh token written to {rt_path}")
