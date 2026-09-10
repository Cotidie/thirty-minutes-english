"""Seed the container's Claude state from the host: a settings.json that keeps
only plugin enablement (so host hooks and permissions never run here) and a
writable copy of the credentials file (claude.ai login plus MCP OAuth tokens),
so token refreshes succeed inside the container."""

import json
import os
import shutil
import sys
from pathlib import Path

HOST_SETTINGS = Path("/host-settings.json")
HOST_CREDENTIALS = Path("/host-credentials.json")
KEEP = ("enabledPlugins", "extraKnownMarketplaces")


def seed() -> None:
    claude_dir = Path.home() / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    if HOST_SETTINGS.exists():
        host = json.loads(HOST_SETTINGS.read_text())
        (claude_dir / "settings.json").write_text(
            json.dumps({k: host[k] for k in KEEP if k in host}, indent=2)
        )
    if HOST_CREDENTIALS.exists():
        target = claude_dir / ".credentials.json"
        shutil.copyfile(HOST_CREDENTIALS, target)
        target.chmod(0o600)


if __name__ == "__main__":
    seed()
    os.execvp(sys.argv[1], sys.argv[1:])
