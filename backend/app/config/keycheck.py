"""One cheap authenticated request per provider, so the settings modal can
say whether a key works before a round depends on it."""

from dataclasses import dataclass

from app.mcp_client import McpError, McpHttp
from app.net import HttpError, request
from app.pictures.painters import COMFY_MCP
from app.voice.assessor import issue_token

GETS = {
    "OPENAI_API_KEY": ("https://api.openai.com/v1/models?limit=1", "Authorization", "Bearer "),
    "GEMINI_API_KEY": ("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", "x-goog-api-key", ""),
    "OPENROUTER_API_KEY": ("https://openrouter.ai/api/v1/key", "Authorization", "Bearer "),
    # The search MCP answers any key (it falls back to keyless), so the REST API is the one that says no.
    "FIRECRAWL_API_KEY": ("https://api.firecrawl.dev/v2/team/credit-usage", "Authorization", "Bearer "),
}
KEYS = (*GETS, "AZURE_SPEECH_KEY", "COMFY_API_KEY")


@dataclass(frozen=True)
class KeyCheck:
    ok: bool
    message: str


def check_key(name: str, key: str, region: str = "") -> KeyCheck:
    """`region` matters only to Azure, whose endpoint is per region."""
    if name not in KEYS:
        raise KeyError(name)
    key, region = key.strip(), region.strip()
    if not key:
        return KeyCheck(False, "no key to test")
    if name == "AZURE_SPEECH_KEY" and not region:
        return KeyCheck(False, "set AZURE_SPEECH_REGION first")
    try:
        if name == "COMFY_API_KEY":
            # comfy-cloud has no REST key endpoint; its MCP server turns a bad key away at connect.
            McpHttp(COMFY_MCP, key, read_timeout_s=15).check()
        elif name == "AZURE_SPEECH_KEY":
            issue_token(key, region)
        else:
            url, header, prefix = GETS[name]
            request("GET", url, {header: prefix + key}, timeout=15)
    except HttpError as e:
        if e.status == 502:
            return KeyCheck(False, f"could not reach the provider: {e.message}")
        return KeyCheck(False, str(e))
    except McpError as e:
        return KeyCheck(False, str(e))
    return KeyCheck(True, "key works")
