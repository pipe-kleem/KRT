"""CC Import panel (Stage 55): Character Creator FBX -> clean cc_built .ma.

Pipeline, in this order (each step is its own function so it can be run or
tested alone from the Script Editor):

    1. import the FBX through Reallusion Auto Setup + Generate Face Rig
       (utils/cc_autosetup.py drives the tool's own window)
    2. import all references      - referenced nodes can't be edited/deleted,
                                     so this must happen BEFORE the deletes
    3. delete all keys            - time-based animCurves only (TL/TA/TU/TT);
                                     driven keys (UL/UA/UU/UT) are kept
    4. delete all bump maps       - bump nodes; deleting a node removes its
                                     connections, and the orphaned normal-map
                                     file nodes go in step 7
    5. remove all namespaces
    5b. delete the meshes listed in the panel (names without namespace)
    5c. move CTRL_faceGUI to the panel's Face GUI position       (Stage 57)
    5d. hide the CC_Base_Body faces listed in HIDE_BODY_FACES     (Stage 57)
    5e. strip the "_a" suffix from transform names                (Stage 57)
    6. repath textures            - one os.walk index of the folder, then
                                     best match per file node (same rules as
                                     IDR RepathTexture: exact > same ext >
                                     EXT_PRIORITY > first)
    7. delete unused nodes        - Maya's own "Delete Unused Nodes"
    8. export <rig root>/cc_rig/cc_built_<version>.ma
"""
import os
import re

import maya.cmds as cmds
import maya.mel as mel

BUMP_TYPES = ("bump2d", "bump3d", "aiBump2d", "aiBump3d")
KEY_CURVE_TYPES = ("animCurveTL", "animCurveTA", "animCurveTU", "animCurveTT")
EXT_PRIORITY = [".exr", ".tx", ".rstex", ".png", ".tga", ".tif", ".tiff",
                ".jpg", ".jpeg", ".bmp", ".hdr"]
# Stage 57 - from the studio's manual post-import script.
FACE_GUI_NODE = "CTRL_faceGUI"
DEFAULT_FACE_GUI_POS = "32.404, 240.963, -6.432"
STRIP_SUFFIX = "_a"
# CC base-body faces hidden in every character (same CC3+ topology).
HIDE_BODY_FACES = [
    "CC_Base_Body.f[219416]",
    "CC_Base_Body.f[216208:216623]", "CC_Base_Body.f[216640:217343]",
    "CC_Base_Body.f[218208:218287]", "CC_Base_Body.f[218352:218431]",
    "CC_Base_Body.f[218480:219759]", "CC_Base_Body.f[217995]",
    "CC_Base_Body.f[215136:216207]", "CC_Base_Body.f[216624:216639]",
    "CC_Base_Body.f[217344:218207]", "CC_Base_Body.f[218288:218351]",
    "CC_Base_Body.f[218432:218479]", "CC_Base_Body.f[219760:219935]",
    "CC_Base_Body.f[224216]",
    "CC_Base_Body.f[221008:221423]", "CC_Base_Body.f[221440:222143]",
    "CC_Base_Body.f[223008:223087]", "CC_Base_Body.f[223152:223231]",
    "CC_Base_Body.f[223280:224559]", "CC_Base_Body.f[222786]",
    "CC_Base_Body.f[219936:221007]", "CC_Base_Body.f[221424:221439]",
    "CC_Base_Body.f[222144:223007]", "CC_Base_Body.f[223088:223151]",
    "CC_Base_Body.f[223232:223279]", "CC_Base_Body.f[224560:224735]",
]

OUTPUT_FOLDER = "cc_rig"
OUTPUT_PREFIX = "cc_built"


def _log(msg):
    print("[KRT CC] " + msg)


def normalize_version(text):
    """'3' / 'v3' / 'V003' -> 'v003'. Anything else is used as typed."""
    t = (text or "").strip()
    m = re.match(r"^[vV]?(\d+)$", t)
    return "v{:03d}".format(int(m.group(1))) if m else t


def output_path(rig_root, version):
    return "{}/{}/{}_{}.ma".format(rig_root.rstrip("/\\").replace("\\", "/"),
                                   OUTPUT_FOLDER, OUTPUT_PREFIX, normalize_version(version))


# ── steps ────────────────────────────────────────────────────────────────
def import_all_references(max_depth=10):
    """Loop because importing a reference can expose ITS child references
    as new top-level ones."""
    count = 0
    for _ in range(max_depth):
        refs = cmds.file(query=True, reference=True) or []
        if not refs:
            break
        for r in refs:
            try:
                # an UNLOADED reference can't be imported - load it first
                if not cmds.referenceQuery(r, isLoaded=True):
                    cmds.file(r, loadReference=True)
                cmds.file(r, importReference=True)
                count += 1
            except Exception as e:
                cmds.warning("[KRT CC] could not import reference {}: {}".format(r, e))
    _log("imported {} reference(s)".format(count))
    return count


def delete_all_keys():
    curves = cmds.ls(type=list(KEY_CURVE_TYPES)) or []
    if curves:
        cmds.delete(curves)
    _log("deleted {} keyframe curve(s)".format(len(curves)))
    return len(curves)


def delete_bump_maps():
    known = set(cmds.allNodeTypes() or [])
    types = [t for t in BUMP_TYPES if t in known]     # ls(type=unknown) would error
    nodes = cmds.ls(type=types) if types else []
    if nodes:
        cmds.delete(nodes)
    _log("deleted {} bump node(s)".format(len(nodes)))
    return len(nodes)


def remove_all_namespaces():
    cmds.namespace(setNamespace=":")
    spaces = cmds.namespaceInfo(":", listOnlyNamespaces=True, recurse=True) or []
    # deepest first, so 'a:b' is merged before 'a'
    spaces = sorted((n.lstrip(":") for n in spaces), key=lambda n: n.count(":"), reverse=True)
    removed = 0
    for ns in spaces:
        if ns in ("UI", "shared") or not cmds.namespace(exists=":" + ns):
            continue
        try:
            cmds.namespace(removeNamespace=":" + ns, mergeNamespaceWithRoot=True)
            removed += 1
        except Exception as e:
            cmds.warning("[KRT CC] could not remove namespace {}: {}".format(ns, e))
    _log("removed {} namespace(s)".format(removed))
    return removed


def delete_meshes(names_text):
    """'Boots, CC_Base_Eye*' -> delete matching transforms. Namespaces in the
    typed names are ignored (they were all removed in the step before)."""
    names = [n.strip().split("|")[-1].split(":")[-1]
             for n in (names_text or "").split(",") if n.strip()]
    deleted, missing = [], []
    for name in names:
        # only transforms that carry a mesh - so a wildcard can never catch
        # a joint or a control that happens to share the name pattern
        found = [t for t in (cmds.ls(name, type="transform", long=True) or [])
                 if cmds.listRelatives(t, shapes=True, type="mesh", fullPath=True)]
        if not found:
            missing.append(name)
            continue
        found = [f for f in found if cmds.objExists(f)]     # a parent may already be gone
        if found:
            cmds.delete(found)
            deleted.extend(found)
    _log("deleted {} mesh transform(s)".format(len(deleted)))
    for m in missing:
        cmds.warning("[KRT CC] delete meshes: nothing named '{}'".format(m))
    return deleted


def position_face_gui(pos_text=DEFAULT_FACE_GUI_POS):
    """Move the face board (CTRL_faceGUI) to 'x, y, z'."""
    if not cmds.objExists(FACE_GUI_NODE):
        cmds.warning("[KRT CC] {} not found - face GUI not moved".format(FACE_GUI_NODE))
        return False
    try:
        x, y, z = [float(v) for v in (pos_text or DEFAULT_FACE_GUI_POS).replace(" ", "").split(",")]
    except ValueError:
        raise ValueError("Face GUI position must be 'x, y, z', got: {!r}".format(pos_text))
    for axis, v in zip("XYZ", (x, y, z)):
        cmds.setAttr("{}.translate{}".format(FACE_GUI_NODE, axis), v)
    _log("{} moved to {}, {}, {}".format(FACE_GUI_NODE, x, y, z))
    return True


def hide_body_faces(faces=None):
    """Select the faces and run Maya's own Hide Selected (component hide)."""
    faces = list(faces or HIDE_BODY_FACES)
    mesh = faces[0].split(".")[0]
    if not cmds.objExists(mesh):
        cmds.warning("[KRT CC] {} not found - faces not hidden".format(mesh))
        return False
    try:
        cmds.select(faces, replace=True)
    except ValueError as e:      # face index out of range = different topology
        cmds.warning("[KRT CC] could not select body faces ({}) - skipped".format(e))
        return False
    mel.eval("HideSelectedObjects;")
    cmds.select(clear=True)
    _log("hid {} face range(s) on {}".format(len(faces), mesh))
    return True


def strip_name_suffix(suffix=STRIP_SUFFIX):
    """'soldier1_a' -> 'soldier1'. Deepest DAG paths first: renaming a
    parent changes every child's long name, so children go first while
    their stored paths are still valid."""
    nodes = cmds.ls("*" + suffix, type="transform", long=True) or []
    nodes.sort(key=lambda n: n.count("|"), reverse=True)
    renamed = 0
    for node in nodes:
        short = node.split("|")[-1]
        if short.endswith(suffix) and len(short) > len(suffix) and cmds.objExists(node):
            cmds.rename(node, short[:-len(suffix)])
            renamed += 1
    _log("stripped '{}' from {} name(s)".format(suffix, renamed))
    return renamed


def _build_index(root):
    """stem(lowercase) -> [full paths], one walk of the whole folder."""
    index = {}
    for walk_root, _dirs, files in os.walk(root):
        walk_root = walk_root.replace("\\", "/")
        for f in files:
            index.setdefault(os.path.splitext(f)[0].lower(), []).append(walk_root + "/" + f)
    return index


def _best_match(index, filename):
    stem, ext = os.path.splitext(filename.lower())
    cands = index.get(stem, [])
    if not cands:
        return None
    for fp in cands:                                  # 1 exact name
        if os.path.basename(fp).lower() == filename.lower():
            return fp
    for fp in cands:                                  # 2 same extension
        if os.path.splitext(fp)[1].lower() == ext:
            return fp
    ranked = [fp for fp in cands if os.path.splitext(fp)[1].lower() in EXT_PRIORITY]
    if ranked:                                        # 3 preferred extension
        return min(ranked, key=lambda fp: EXT_PRIORITY.index(os.path.splitext(fp)[1].lower()))
    return cands[0]                                   # 4 anything


def repath_textures(tex_dir):
    tex_dir = (tex_dir or "").strip().replace("\\", "/")
    if not tex_dir:
        _log("no texture folder given - repath skipped")
        return 0, 0
    if not os.path.isdir(tex_dir):
        raise IOError("Texture folder not found: " + tex_dir)
    index = _build_index(tex_dir)
    nodes = cmds.ls(type="file") or []
    done, missing = 0, []
    for node in nodes:
        old = (cmds.getAttr(node + ".fileTextureName") or "").replace("\\", "/")
        new = _best_match(index, os.path.basename(old)) if old else None
        if new:
            cmds.setAttr(node + ".fileTextureName", new, type="string")
            done += 1
        else:
            missing.append("{} ({})".format(node, os.path.basename(old) or "empty"))
    _log("repathed {}/{} texture(s) into {}".format(done, len(nodes), tex_dir))
    for m in missing:
        cmds.warning("[KRT CC] texture not found in folder: " + m)
    return done, len(nodes)


def delete_unused_nodes():
    before = len(cmds.ls() or [])
    try:
        mel.eval("MLdeleteUnused;")
    except Exception:
        mel.eval('source "MLdeleteUnused.mel"; MLdeleteUnused;')
    after = len(cmds.ls() or [])
    _log("delete unused nodes: {} node(s) removed".format(before - after))
    return before - after


def export_ma(path):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    if os.path.exists(path):
        cmds.warning("[KRT CC] overwriting existing " + path)
    # exportAll writes the scene to a new file WITHOUT renaming the open
    # scene, so the rest of the build keeps its own scene name.
    cmds.file(path, exportAll=True, type="mayaAscii", force=True,
              preserveReferences=False)
    _log("saved " + path)
    return path


# ── speed (Stage 58) ─────────────────────────────────────────────────────
class _FastMode(object):
    """Context manager that removes Maya overhead around heavy scene work.

    Stage 60: Maya CRASHED at ~70% of the FBX import once v44.7 wrapped the
    Auto Setup import in all three switches. Suspending the viewport and the
    undo queue while a compiled third-party tool builds HIK + VP2/Arnold
    shaders is the prime suspect, so those two are now opt-in and used
    only around KRT's OWN cleanup steps (plain cmds calls). The import
    itself only gets the echo switch, which just stops printing.

    - Script Editor "Echo All Commands" OFF: with it on, Auto Setup's FBX
      import prints thousands of progressBar/MEL lines, and printing to the
      Script Editor is slow.
    - undo queue OFF: every node Auto Setup/cleanup creates is otherwise
      recorded for undo. A pipeline step never needs undoing inside itself.
    - viewport refresh suspended: no redraw of a half-built, fully textured
      character after every command.
    Everything is restored in __exit__, even if a step raises."""

    def __init__(self, undo_off=False, suspend_viewport=False):
        self.undo_off = undo_off
        self.suspend_viewport = suspend_viewport

    def __enter__(self):
        self._echo = cmds.scriptEditorInfo(query=True, echoAllCommands=True)
        self._undo = cmds.undoInfo(query=True, state=True)
        cmds.scriptEditorInfo(echoAllCommands=False)
        if self.undo_off:
            cmds.undoInfo(stateWithoutFlush=False)
        if self.suspend_viewport:
            cmds.refresh(suspend=True)
        return self

    def __exit__(self, *exc):
        try:
            if self.suspend_viewport:
                cmds.refresh(suspend=False)
                cmds.refresh(force=True)
        finally:
            if self.undo_off:
                cmds.undoInfo(stateWithoutFlush=self._undo)
            cmds.scriptEditorInfo(echoAllCommands=self._echo)


class _Timer(object):
    """Collects how long each step takes -> printed as a table at the end,
    so we know WHICH step is slow before trying to speed anything up."""

    def __init__(self):
        self.rows = []

    def step(self, name, fn, *args, **kwargs):
        import time
        t = time.time()
        try:
            return fn(*args, **kwargs)
        finally:
            self.rows.append((name, time.time() - t))

    def report(self):
        total = sum(t for _, t in self.rows) or 1.0
        _log("timing:")
        for name, t in self.rows:
            print("    {:<28} {:7.1f}s  {:5.1f}%".format(name, t, 100.0 * t / total))
        print("    {:<28} {:7.1f}s".format("TOTAL", total))


# ── whole pipeline ───────────────────────────────────────────────────────
def run(fbx, version, rig_root, tex_dir="", new_scene=True, face_rig=True,
        delete_meshes_text="", face_gui_pos=DEFAULT_FACE_GUI_POS):
    """Returns (success, error_message) like every other KRT *_logic()."""
    import traceback
    try:
        fbx = (fbx or "").strip()
        if not fbx or not os.path.isfile(fbx):
            return False, "FBX not found: {}".format(fbx or "(empty)")
        if not (version or "").strip():
            return False, "Enter a CC version (e.g. v001)."
        if not rig_root:
            return False, "Rig Root is not set - the output goes to <Rig Root>/cc_rig/."
        out = output_path(rig_root, version)

        if new_scene:
            cmds.file(new=True, force=True)
        from . import cc_autosetup
        t = _Timer()
        try:
            # the third-party import: echo off only (see _FastMode)
            with _FastMode():
                t.step("Auto Setup import+face", cc_autosetup.run, fbx, face_rig=face_rig)
            # KRT's own cleanup: full fast mode
            with _FastMode(undo_off=True, suspend_viewport=True):
                t.step("import references", import_all_references)
                t.step("delete keys", delete_all_keys)
                t.step("delete bump maps", delete_bump_maps)
                t.step("remove namespaces", remove_all_namespaces)
                t.step("delete meshes", delete_meshes, delete_meshes_text)
                t.step("face GUI position", position_face_gui, face_gui_pos)
                t.step("hide body faces", hide_body_faces)
                t.step("strip _a suffix", strip_name_suffix)
                t.step("repath textures", repath_textures, tex_dir)
                t.step("delete unused nodes", delete_unused_nodes)
                t.step("export .ma", export_ma, out)
        finally:
            t.report()
        return True, ""
    except Exception:
        return False, traceback.format_exc()
