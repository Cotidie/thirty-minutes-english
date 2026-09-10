"""Seed the container's Claude settings from the host, keeping only plugin
enablement so host hooks and permissions never run inside the container."""

import json
import os
import sys
from pathlib import Path

HOST_SETTINGS = Path("/host-settings.json")
KEEP = ("enabledPlugins", "extraKnownMarketplaces")


def seed_settings() -> None:
    if not HOST_SETTINGS.exists():
        return
    host = json.loads(HOST_SETTINGS.read_text())
    target = Path.home() / ".claude" / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({k: host[k] for k in KEEP if k in host}, indent=2))


if __name__ == "__main__":
    seed_settings()
    os.execvp(sys.argv[1], sys.argv[1:])
