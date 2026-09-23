"""The host's Claude skills (~/.claude/skills, mounted read-only), offered as extras on top
of the app's own writing skill. Each is a folder with a SKILL.md whose frontmatter names it."""

from pathlib import Path

import yaml

SKILLS_DIR = Path.home() / ".claude" / "skills"


def host_skills(root: Path = SKILLS_DIR) -> dict[str, str]:
    """Skill name to its one-line description, sorted by name. Folders without a readable
    SKILL.md (a broken symlink, say) are left out; no folder at all gives none."""
    found: dict[str, str] = {}
    for folder in sorted(root.glob("*")) if root.is_dir() else ():
        meta = frontmatter(folder / "SKILL.md")
        if meta is None:
            continue
        name = str(meta.get("name") or folder.name)
        found[name] = " ".join(str(meta.get("description") or "").split())
    return dict(sorted(found.items()))


def frontmatter(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return {}
    head, _, _ = text[3:].partition("\n---")
    try:
        meta = yaml.safe_load(head)
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}
