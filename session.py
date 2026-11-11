import maya.cmds as cmds
import maya.OpenMaya as om
import os
import re
import json
import hashlib

class SessionManager:
    def __init__(self):
        self.base_dir = os.path.join(cmds.internalVar(userAppDir=True), "KRT").replace("\\", "/")
        self.autosave_dir = os.path.join(self.base_dir, "autosaves").replace("\\", "/")
        self.cache_dir = os.path.join(self.base_dir, "step_caches").replace("\\", "/")
        self.session_file = os.path.join(self.base_dir, "session_data.json").replace("\\", "/")

        for d in [self.base_dir, self.autosave_dir, self.cache_dir]:
            if not os.path.exists(d): os.makedirs(d)
            
        self.data = {
            "auto_save_enabled": True,
            "recent_files": [],
            "autosave_files": [],
            "published_files": [],
            # Free-form notes for this user on this machine. Not tied to any
            # pipeline file - always loaded, regardless of which session/LOD
            # JSON is open, so it reads back the same every time KRT starts.
            "user_notes": "",
            # Most-recently-added mGear component/Plebe entries in the Module
            # Graph Editor's Tab search popup, newest first - lets that
            # search surface what this user actually reaches for instead of
            # only an alphabetical list of every Shifter component.
            "recent_modules": [],
            # Stage 17: Rigging Workspace script/tools library root. Defaults
            # to the studio path; if a user changes it via the Rigging
            # Workspace tab, this is what saves that override for them.
            "scripts_library_path": r"P:\pipeline_database\Maya\Scripts\ONE"
        }
        self.load_session()
        
    def load_session(self):
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception as e:
                om.MGlobal.displayWarning(f"Could not read session file: {e}")
    
    def save_session(self):
        try:
            with open(self.session_file, 'w') as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            om.MGlobal.displayError(f"Could not save session file: {e}")
            
    # Stage 67: a step cache is <folder>/<panel uuid>.ma. The folder is per
    # pipeline JSON PATH, but the uuid is saved in the JSON and stays the same
    # across every version/copy of it - so a cache written while v001 was open
    # is still that step's cache when v002 (or a copy) is loaded. These two
    # search every step_caches/ subfolder by uuid. One scan is reused for a
    # couple of seconds, so refreshing 40 panels costs one directory walk.
    _CACHE_INDEX_TTL = 2.0

    def _cache_index(self, force=False):
        import time as _time
        now = _time.time()
        idx = getattr(self, "_cache_idx", None)
        if idx is not None and not force and now - getattr(self, "_cache_idx_t", 0) < self._CACHE_INDEX_TTL:
            return idx
        idx = {}
        try:
            for sub in os.listdir(self.cache_dir):
                d = os.path.join(self.cache_dir, sub)
                if not os.path.isdir(d):
                    continue
                for fn in os.listdir(d):
                    if fn.lower().endswith(".ma"):
                        p = os.path.join(d, fn).replace("\\", "/")
                        try:
                            idx.setdefault(fn[:-3], []).append((os.path.getmtime(p), p))
                        except OSError:
                            pass
        except OSError:
            pass
        for k in idx:
            idx[k] = [p for _, p in sorted(idx[k], reverse=True)]   # newest first
        self._cache_idx, self._cache_idx_t = idx, now
        return idx

    def invalidate_cache_index(self):
        self._cache_idx = None

    def find_caches(self, uuid_hex, rig_prefix=""):
        """Every cache file for this step uuid, newest first, in the cache
        folders of THIS rig only: a folder is named after its pipeline JSON
        (kva_a_Rig_v001_1a2b3c4d), so it must start with `rig_prefix` (the
        rig folder name, e.g. kva_a). That keeps a JSON copied from another
        character - same panel uuids - from showing that character's caches.
        '_unsaved' (caches made before the first save) is always searched."""
        if not uuid_hex:
            return []
        pre = (rig_prefix or "").lower()
        out = []
        for p in self._cache_index().get(uuid_hex, []):
            folder = os.path.basename(os.path.dirname(p)).lower()
            if pre and folder != "_unsaved" and not folder.startswith(pre):
                continue
            if not pre and folder != "_unsaved":
                continue
            if os.path.isfile(p):
                out.append(p)
        return out

    def cache_dir_for(self, session_path):
        """Return (and create) the step-cache subfolder for a given pipeline JSON.
        Each JSON gets its own folder under step_caches/ so caches for different
        rigs never mix, and reopening the same JSON finds its own caches.
        Unsaved sessions share the '_unsaved' folder."""
        if session_path:
            base = os.path.splitext(os.path.basename(session_path))[0]
            safe = re.sub(r'[^A-Za-z0-9_.-]', '_', base) or "session"
            # Short hash of the full path disambiguates same-named JSONs in
            # different folders while keeping the name human-readable.
            h = hashlib.md5(session_path.replace("\\", "/").lower().encode("utf-8")).hexdigest()[:8]
            sub = "{}_{}".format(safe, h)
        else:
            sub = "_unsaved"
        d = os.path.join(self.cache_dir, sub).replace("\\", "/")
        if not os.path.exists(d):
            try:
                os.makedirs(d)
            except Exception:
                pass
        return d

    def add_recent(self, path):
        if path in self.data["recent_files"]: self.data["recent_files"].remove(path)
        self.data["recent_files"].insert(0, path)
        self.data["recent_files"] = self.data["recent_files"][:15] 
        self.save_session()

    def add_autosave(self, path):
        self.data["autosave_files"].insert(0, path)
        self.data["autosave_files"] = self.data["autosave_files"][:20] 
        self.save_session()

    def get_notes(self):
        return self.data.get("user_notes", "")

    def set_notes(self, text):
        self.data["user_notes"] = text
        self.save_session()

    def get_recent_modules(self):
        return self.data.get("recent_modules", [])

    def add_recent_module(self, module_name):
        recents = self.data.get("recent_modules", [])
        if module_name in recents:
            recents.remove(module_name)
        recents.insert(0, module_name)
        self.data["recent_modules"] = recents[:8]
        self.save_session()

    def add_published(self, path):
        if path in self.data["published_files"]: self.data["published_files"].remove(path)
        self.data["published_files"].insert(0, path)
        self.data["published_files"] = self.data["published_files"][:15] 
        self.save_session()