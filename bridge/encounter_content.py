"""Load encounter content from markdown files with YAML frontmatter."""

import re
from pathlib import Path


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split '---\\n...\\n---\\n<body>' into (metadata dict, body).
    Supports simple key: value pairs and key:\\n  - list items.
    """
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.groups()
    meta = {}
    current_list_key = None
    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            current_list_key = None
            continue
        # List item (indented dash)
        if stripped.startswith("- ") and current_list_key:
            item = stripped[2:].strip().strip('"').strip("'")
            meta[current_list_key].append(item)
            continue
        if ":" not in stripped:
            current_list_key = None
            continue
        k, v = stripped.split(":", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if not v:
            # Start of a list (e.g. "choices:")
            meta[k] = []
            current_list_key = k
            continue
        current_list_key = None
        # Simple type coercion
        if v.lower() in ("true", "false"):
            v = v.lower() == "true"
        elif re.match(r"^-?\d+$", v):
            v = int(v)
        elif re.match(r"^-?\d+\.\d+$", v):
            v = float(v)
        meta[k] = v
    return meta, body.strip()


def load_encounters(pack_dir: Path) -> dict[str, dict]:
    """Load all encounters from packs/<id>/encounters/. Returns {id: encounter}."""
    out = {}
    enc_dir = pack_dir / "encounters"
    if not enc_dir.exists():
        return out
    for md in enc_dir.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        eid = meta.get("id") or md.stem
        out[eid] = {"id": eid, "meta": meta, "body": body, "path": str(md)}
    return out


def validate_encounter(enc: dict) -> list[str]:
    """Return list of problems (empty if valid)."""
    errors = []
    meta = enc["meta"]
    if not meta.get("type"):
        errors.append(f"{enc['id']}: missing 'type'")
    if not meta.get("meeting") in ("green", "yellow", "red", None):
        errors.append(f"{enc['id']}: invalid meeting tag")
    if not enc["body"]:
        errors.append(f"{enc['id']}: empty body")
    return errors
