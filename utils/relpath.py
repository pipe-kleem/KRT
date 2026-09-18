"""Rig-root relative paths (Stage 41).

A pipeline JSON used to store every path in full, e.g.
    P:/rigging_team/Rigging_local_share/all_Rigs/blindfold_a/scripts/utils.py
Now the rig has ONE root folder (shown once in the Rig page header) and every
field under it stores only the part below the root:  scripts/utils.py

Two operations, both pure string work so they can be unit-tested outside Maya:
    resolve(root, "scripts/utils.py")  -> "P:/.../blindfold_a/scripts/utils.py"
    relativize(root, "P:/.../blindfold_a/scripts/utils.py") -> "scripts/utils.py"

Anything that is NOT a path (inline script code, GRAPH::uuid bubble ids,
empty strings) passes through both functions unchanged, so callers can wrap
a field's text blindly without first asking what kind of field it is.
"""
import os
import re

_ABS_RE = re.compile(r"^([a-zA-Z]:[\\/]|\\\\|//|/|~)")
# Characters that can never appear in a Windows path. Their presence means
# "this is code / an id, not a path". ':' is allowed only as a drive letter,
# which _ABS_RE already catches before we get here.
_NOT_PATH_RE = re.compile(r'[<>:"|?*\(\)\n\r=]')


def norm(p):
    """Forward slashes, no trailing slash (except a bare drive root)."""
    p = (p or "").strip().replace("\\", "/")
    while len(p) > 3 and p.endswith("/"):
        p = p[:-1]
    return p


def is_absolute(p):
    return bool(_ABS_RE.match((p or "").strip()))


def looks_like_relative_path(p):
    """True for 'scripts/utils.py', 'model/export.abc', 'ctrl', '.'.
    False for inline code, GRAPH::uuid ids, and absolute paths."""
    p = (p or "").strip()
    if not p or is_absolute(p) or _NOT_PATH_RE.search(p):
        return False
    return True


def resolve(root, p):
    """Return an absolute path for `p` under `root`. Non-path text and
    already-absolute paths come back untouched (only whitespace stripped
    off absolute ones)."""
    if p is None:
        return ""
    text = p.strip()
    root = norm(root)
    if not root or not looks_like_relative_path(text):
        return p if not is_absolute(text) else text
    rel = norm(text)
    if rel in (".", ""):
        return root
    if rel.startswith("./"):
        rel = rel[2:]
    return root + "/" + rel


def relativize(root, p):
    """If `p` lives under `root`, return the part below the root
    ('.' when it IS the root). Otherwise return `p` unchanged."""
    if p is None:
        return ""
    root = norm(root)
    if not root or not is_absolute(p):
        return p
    full = norm(p)
    if os.name == "nt" or True:   # studio paths are Windows; compare case-insensitively
        cmp_full, cmp_root = full.lower(), root.lower()
    else:
        cmp_full, cmp_root = full, root
    if cmp_full == cmp_root:
        return "."
    if cmp_full.startswith(cmp_root + "/"):
        return full[len(root) + 1:]
    return p


def relativize_in_text(root, text):
    """Best-effort: rewrite absolute occurrences of `root` inside a blob of
    text (e.g. an inline script that hardcodes a path). Only used by the
    optional 'Make everything relative' action, never automatically."""
    root = norm(root)
    if not root or not text:
        return text
    pattern = re.compile(re.escape(root).replace("/", r"[\\/]") + r"[\\/]?", re.IGNORECASE)
    return pattern.sub("", text)
