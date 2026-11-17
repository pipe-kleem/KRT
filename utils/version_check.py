"""version_check - is a file the latest version? what other versions exist?

Used by the panels' red/green path field and their 'Versions' button. A version is either
  * a sibling file  <name>_vNN.<ext>   in the same folder, or
  * a sibling folder vNN/ that holds a file of the same extension (.../v04/x_v04.blend -> .../v05/x_v05.blend).
Directory listings are cached for a few seconds so a pipeline with dozens of panels does not hit the server
once per panel.
"""
import os
import re
import time

_CACHE = {}
_TTL = 5.0


def _listdir(folder, fresh=False):
    now = time.time()
    hit = _CACHE.get(folder)
    if hit and not fresh and now - hit[0] < _TTL:
        return hit[1]
    try:
        names = os.listdir(folder)
    except OSError:
        names = []
    _CACHE[folder] = (now, names)
    return names


def _folder_candidate(parent, name, number_text, fname, folder_digits, ext, fresh=False):
    """The file inside sibling version folder `name` that matches `fname`, or None."""
    cand_dir = os.path.join(parent, name)
    blends = [f for f in _listdir(cand_dir, fresh) if f.lower().endswith(ext.lower())]
    if not blends:
        return None
    same = re.sub(r"_v\d+(?=\.[^.]+$)", "_v" + number_text.zfill(max(2, folder_digits)), fname, flags=re.I)
    if same in blends:
        return os.path.join(cand_dir, same)
    try:
        newest = sorted(blends, key=lambda f: os.path.getmtime(os.path.join(cand_dir, f)))[-1]
    except OSError:
        newest = blends[-1]
    return os.path.join(cand_dir, newest)


def latest_info(path, fresh=False, loose=False):
    """-> (state, newer_path). state: 'latest' | 'old' | 'unknown' ('unknown' = no version in the name/folder
    or the file is missing)."""
    if not path or not os.path.isfile(path):
        return "unknown", ""
    d = os.path.dirname(path)
    fname = os.path.basename(path)
    stem, ext = os.path.splitext(fname)
    known = False
    newer_n, newer_path = -1, ""

    # trailing version tokens: _v03 or _v03_v003 (blend version + export counter) - compared as a tuple
    m = re.search(r"((?:_v\d+)+)$", stem, re.I)
    if m or loose:
        known = True
        cur_t = tuple(int(x) for x in re.findall(r"_v(\d+)", m.group(1), re.I)) if m else (0,)
        base = stem[:m.start()] if m else stem
        best_t = None
        for n in _listdir(d, fresh):
            s2, e2 = os.path.splitext(n)
            if e2.lower() != ext.lower():
                continue
            mm = re.match(r"^" + re.escape(base) + r"((?:_v\d+)+)$", s2, re.I)
            if not mm:
                continue
            t2 = tuple(int(x) for x in re.findall(r"_v(\d+)", mm.group(1), re.I))
            if t2 > cur_t and (best_t is None or t2 > best_t):
                best_t, newer_path = t2, os.path.join(d, n)
        if best_t is not None:
            newer_n = best_t[0]

    fm = re.match(r"^v(\d+)$", os.path.basename(d), re.I)
    if fm:
        known = True
        folder_n = int(fm.group(1))
        parent = os.path.dirname(d)
        for n in _listdir(parent, fresh):
            sm = re.match(r"^v(\d+)$", n, re.I)
            if not sm or int(sm.group(1)) <= folder_n or int(sm.group(1)) <= newer_n:
                continue
            cand = _folder_candidate(parent, n, sm.group(1), fname, len(fm.group(1)), ext, fresh)
            if cand:
                newer_n, newer_path = int(sm.group(1)), cand

    if newer_path:
        return "old", newer_path
    return ("latest", "") if known else ("unknown", "")


def all_versions(path, fresh=False, loose=False):
    """[(number, path), ...] every version of this file, oldest first, each once, always including `path`."""
    if not path or not os.path.isfile(path):
        return []
    found = {}
    d = os.path.dirname(path)
    fname = os.path.basename(path)
    stem, ext = os.path.splitext(fname)
    if loose or re.search(r"_v(\d+)$", stem, re.I):
        base = re.sub(r"_v\d+$", "", stem, flags=re.I)
        for n in _listdir(d, fresh):
            s2, e2 = os.path.splitext(n)
            mm = re.match(r"^" + re.escape(base) + r"_v(\d+)$", s2, re.I)
            if mm and e2.lower() == ext.lower():
                found[int(mm.group(1))] = os.path.join(d, n)
            elif loose and s2 == base and e2.lower() == ext.lower():
                found[0] = os.path.join(d, n)
    fm = re.match(r"^v(\d+)$", os.path.basename(d), re.I)
    if fm:
        parent = os.path.dirname(d)
        for n in _listdir(parent, fresh):
            sm = re.match(r"^v(\d+)$", n, re.I)
            if not sm:
                continue
            cand = _folder_candidate(parent, n, sm.group(1), fname, len(fm.group(1)), ext, fresh)
            if cand:
                found.setdefault(int(sm.group(1)) + 100000, cand)       # folder versions sort after file versions
    cur_key = os.path.normcase(os.path.abspath(path))
    if cur_key not in [os.path.normcase(os.path.abspath(v)) for v in found.values()]:
        found[-1] = path
    best = {}
    for k, v in found.items():
        nk = os.path.normcase(os.path.abspath(v))
        if nk not in best or k > best[nk][0]:
            best[nk] = (k, v)
    return sorted(((k % 100000 if k >= 0 else k), v) for k, v in best.values())


_GROUPS = ((".ma", ".mb", ".fbx", ".obj", ".abc"),)


def folder_files(path, fresh=False, limit=150):
    """Every file in the same folder with the same kind of extension as `path` (3D files count as one kind),
    whatever its name or version - [(mtime, full_path), ...] newest first, `path` always included.
    Only lists the folder and reads dates; nothing is changed."""
    if not path:
        return []
    d = os.path.dirname(path)
    ext = os.path.splitext(path)[1].lower()
    exts = next((g for g in _GROUPS if ext in g), (ext,))
    out = []
    for n in _listdir(d, fresh):
        if os.path.splitext(n)[1].lower() in exts:
            fp = os.path.join(d, n)
            try:
                if os.path.isfile(fp):
                    out.append((os.path.getmtime(fp), fp))
            except OSError:
                pass
    out.sort(key=lambda x: x[0], reverse=True)
    out = out[:limit]
    cur = os.path.normcase(os.path.abspath(path))
    if os.path.isfile(path) and cur not in [os.path.normcase(os.path.abspath(f)) for _t, f in out]:
        out.append((os.path.getmtime(path), path))
    return out
