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