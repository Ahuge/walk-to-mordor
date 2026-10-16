"""Load encounter content from markdown files with YAML frontmatter."""

import re
from pathlib import Path


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split '---\\n...\\n---\\n<body>' into (metadata dict, body).
    Supports:
      key: value          (with int/float/bool coercion)
      key:                (empty value)
        - list item
        - list item
      key:
        subkey: value     (nested dict)
        subkey: value
    """
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.groups()
    lines = raw.split("\n")
    meta = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            i += 1
            continue
        k, v = stripped.split(":", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v:
            # Simple key: value
            if v.lower() in ("true", "false"):
                v = v.lower() == "true"
            elif re.match(r"^-?\d+$", v):
                v = int(v)
            elif re.match(r"^-?\d+\.\d+$", v):
                v = float(v)
            meta[k] = v
            i += 1
            continue
        # Empty value: look ahead for list (-) or dict (key:) items
        j = i + 1
        items = []
        is_dict = False
        is_list = False
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt:
                j += 1
                continue
            # Stop at non-indented line (new top-level key)
            if lines[j] and not lines[j][0].isspace():
                break
            if nxt.startswith("- "):
                is_list = True
                items.append(nxt[2:].strip().strip('"').strip("'"))
            elif ":" in nxt:
                is_dict = True
                sk, sv = nxt.split(":", 1)
                items.append((sk.strip(), sv.strip().strip('"').strip("'")))
            else:
                break
            j += 1
        if is_dict:
            meta[k] = dict(items)
        elif is_list:
            meta[k] = items
        else:
            meta[k] = ""
        i = j
    return meta, body.strip()


def validate_encounter(enc: dict) -> list[str]:
    """Check an encounter for common issues. Returns list of error strings."""
    errors = []
    eid = enc.get("id", "?")
    meta = enc.get("meta", {})
    body = enc.get("body", "")
    if not meta.get("type"):
        errors.append(f"{eid}: missing type")
    elif meta["type"] not in ("vignette", "choice", "challenge", "companion",
                              "tale", "poi", "unlock"):
        errors.append(f"{eid}: unknown type '{meta['type']}'")
    if not body.strip():
        errors.append(f"{eid}: empty body")
    if meta.get("type") == "choice":
        choices = meta.get("choices", [])
        if not choices:
            errors.append(f"{eid}: choice type but no choices defined")
        for c in choices:
            parts = c.split(":", 2)
            if len(parts) < 2:
                errors.append(f"{eid}: malformed choice '{c}'")
        # Check followups match choice IDs
        followups = meta.get("followups", {})
        if isinstance(followups, dict):
            choice_ids = {c.split(":", 1)[0].strip() for c in choices}
            for fid in followups:
                if fid not in choice_ids:
                    errors.append(f"{eid}: followup '{fid}' has no matching choice")
    if meta.get("type") == "challenge":
        ctype = meta.get("challenge_type")
        if ctype not in ("speed", "stealth", "incline"):
            errors.append(f"{eid}: invalid challenge_type '{ctype}'")
    return errors


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
