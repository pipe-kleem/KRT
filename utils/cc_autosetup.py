"""KRT copy of C:/pipeline/ssd_cc_autosetup/ssd_cc_autosetup.py (Stage 55).

Kept inside the KRT package so the installer ships it with KRT; the
standalone file stays for use outside KRT. Fix bugs in BOTH copies.

ssd_cc_autosetup - Character Creator "Auto Setup for Maya" in one line.

Does what you do by hand in the Auto Setup window:
    1. Import tab  -> set FBX (+ JSON next to it) -> click Import
    2. select the new character's root joint (CC_Base_BoneRoot)
    3. Face Rig tab -> click Generate Face Rig

Usage (Maya Script Editor, Python tab):
    import ssd_cc_autosetup as cc
    cc.run(r"C:/Users/sid2/Downloads/fix/lod_1/soldier1.Fbx")

    # many characters, each in a fresh scene, saved as .ma next to its FBX:
    cc.run_many([r"C:/.../a.Fbx", r"C:/.../b.Fbx"], save=True)

    # if something fails, print what the Auto Setup window contains:
    cc.inspect_ui()

HOW IT WORKS: Auto Setup ships as compiled .pyd files, so its code can't be
read or called directly with confidence. Instead this script drives the
tool's OWN window: it finds the widgets by their visible text ("Import",
"Face Rig", "Generate Face Rig") and clicks them - exactly the same code
runs as when you click. If Reallusion changes a label, update the TEXT_*
constants below.
"""
import os
import sys
import time

import maya.cmds as cmds
import maya.utils

from ..compat import QtWidgets, QtCore

__version__ = "1.0"

# Visible labels in the Auto Setup window (from the screenshots, v1.0.4).
TEXT_IMPORT_TAB = "Import"
TEXT_FACE_TAB = "Face Rig"
TEXT_IMPORT_BTN = "Import"
TEXT_FACE_BTN = "Generate Face Rig"
ROOT_JOINT = "CC_Base_BoneRoot"

# Where Auto Setup may be installed - first one that exists wins.
def _candidate_paths():
    user_maya = cmds.internalVar(userAppDir=True)          # C:/Users/<you>/Documents/maya/
    return [
        os.path.join(user_maya, "scripts", "AutoSetupForMaya"),
        r"C:/pipeline/CC_Auto_Setup_for_Maya_2026/AutoSetupForMaya",
    ]


def _log(msg):
    print("[ssd_cc_autosetup] " + msg)


# ── helpers ──────────────────────────────────────────────────────────────
def _pump(seconds=0.3):
    """Let Qt and Maya process pending events for a moment.
    Buttons, tabs and scriptJobs often update on the NEXT event-loop turn,
    so after every click we give the UI a chance to catch up."""
    end = time.time() + seconds
    app = QtWidgets.QApplication.instance()
    while True:
        app.processEvents()
        try:
            maya.utils.processIdleEvents()
        except Exception:
            pass
        if time.time() >= end:
            break
        time.sleep(0.02)


def _wait_for(predicate, timeout, what):
    """Pump events until predicate() is truthy, or raise after `timeout` s."""
    end = time.time() + timeout
    while time.time() < end:
        result = predicate()
        if result:
            return result
        _pump(0.2)
    raise RuntimeError("Timed out after {}s waiting for: {}".format(timeout, what))


def _btn_text(w):
    return (w.text() or "").replace("&", "").strip()


def _find_main_tabs():
    """The Auto Setup QTabWidget = the one that has BOTH an Import and a
    Face Rig tab. Searching by tab text avoids depending on object names."""
    for w in QtWidgets.QApplication.allWidgets():
        if isinstance(w, QtWidgets.QTabWidget):
            names = [w.tabText(i).replace("&", "").strip() for i in range(w.count())]
            if TEXT_IMPORT_TAB in names and TEXT_FACE_TAB in names:
                return w
    return None


def _tab_page(tabs, title):
    for i in range(tabs.count()):
        if tabs.tabText(i).replace("&", "").strip() == title:
            return i, tabs.widget(i)
    raise RuntimeError("No '{}' tab in Auto Setup".format(title))


def _find_button(parent, text):
    for b in parent.findChildren(QtWidgets.QAbstractButton):
        if _btn_text(b) == text:
            return b
    return None


def _cc_roots():
    return set(cmds.ls(ROOT_JOINT, "*:" + ROOT_JOINT, "*:*:" + ROOT_JOINT,
                       type="joint", long=True) or [])


# ── auto-close popups ────────────────────────────────────────────────────
class _PopupCloser(QtCore.QObject):
    """Clicks OK on any NEW dialog/message box that appears while we run
    (e.g. an import-result message). A QTimer keeps firing even inside a
    modal dialog's own event loop, which is why this works for modal
    popups that would otherwise block the script."""

    def __init__(self):
        super(_PopupCloser, self).__init__()
        self._before = set(id(w) for w in QtWidgets.QApplication.topLevelWidgets())
        self.closed = []
        self._timer = QtCore.QTimer()
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        for w in QtWidgets.QApplication.topLevelWidgets():
            if id(w) in self._before or not w.isVisible():
                continue
            if not isinstance(w, QtWidgets.QDialog):
                continue
            label = w.windowTitle() or type(w).__name__
            if isinstance(w, QtWidgets.QMessageBox):
                label += ": " + (w.text() or "")[:120]
                btn = w.defaultButton() or (w.buttons()[0] if w.buttons() else None)
                if btn is not None:
                    btn.click()
                else:
                    w.accept()
            else:
                w.accept()
            self._before.add(id(w))
            self.closed.append(label)
            _log("auto-closed popup -> " + label)


# ── environment checks (v45.1) ───────────────────────────────────────────
def _isolate_autosetup_imports(root):
    """Auto Setup's own code imports its sub-packages by BARE name
    ('import widgets', 'from SceneInspector import ...'), relying on its
    lib/ folder being on sys.path. Python takes the FIRST match on sys.path,
    so any other folder on sys.path with a 'widgets' package wins - e.g. a
    KRT copy (KRT has widgets/ too), which failed with 'attempted relative
    import beyond top-level package'. So: put lib/ FIRST, and drop any
    already-imported module of the same name that came from elsewhere."""
    lib = os.path.join(root, "lib").replace("\\", "/")
    if not os.path.isdir(lib):
        return
    while lib in sys.path:
        sys.path.remove(lib)
    sys.path.insert(0, lib)
    names = set()
    for entry in os.listdir(lib):
        base = entry.split(".")[0]           # FBXImporter.cp311-win_amd64.pyd -> FBXImporter
        if base and not base.startswith("_"):
            names.add(base)
    root_n = os.path.normcase(os.path.abspath(root))
    for name in names:
        mod = sys.modules.get(name)
        f = getattr(mod, "__file__", None) if mod else None
        if f and not os.path.normcase(os.path.abspath(f)).startswith(root_n):
            _log("unloading foreign module '{}' from {}".format(name, f))
            for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
                del sys.modules[key]


def _check_pymel():
    """Auto Setup runs on PyMEL. Maya 2026 needs PyMEL 1.7+ (Auto Setup ships
    pymel-1.7.1rc1 in its wheels/ folder). An older PyMEL earlier on sys.path
    - e.g. one bundled inside another tool - gets imported instead and can
    crash Maya in the middle of the FBX import. Stop before that happens."""
    try:
        import pymel
    except ImportError:
        return                                  # Auto Setup reports this itself
    ver = getattr(pymel, "__version__", "0")
    path = os.path.dirname(getattr(pymel, "__file__", "") or "")
    _log("PyMEL {} from {}".format(ver, path))
    import re as _re
    nums = [int(n) for n in _re.findall(r"\d+", ver)[:2]] + [0, 0]
    maya_ver = int(cmds.about(apiVersion=True)) // 10000
    if maya_ver >= 2026 and (nums[0], nums[1]) < (1, 7):
        raise RuntimeError(
            "PyMEL {} is loaded from\n  {}\nMaya {} needs PyMEL 1.7 or newer - an older one can crash "
            "Maya during the Auto Setup FBX import.\nFix: run AutoSetupForMaya/install_pymel.bat, and "
            "remove that folder from PYTHONPATH / Maya.env / userSetup so it is not found first."
            .format(ver, path, maya_ver))


# ── main steps ───────────────────────────────────────────────────────────
def open_ui():
    """Open (or reuse) the Auto Setup window and return its tab widget."""
    tabs = _find_main_tabs()
    if tabs is not None and tabs.isVisible():
        return tabs
    for p in _candidate_paths():
        if os.path.isdir(p):
            if p not in sys.path:
                sys.path.append(p)
            break
    else:
        raise RuntimeError("Auto Setup not found in: " + ", ".join(_candidate_paths()))
    _isolate_autosetup_imports(p)
    _check_pymel()
    import AutoSetupMain
    AutoSetupMain.main()
    return _wait_for(lambda: (_find_main_tabs() if (_find_main_tabs() and _find_main_tabs().isVisible()) else None),
                     30, "the Auto Setup window to open")


class _FileDialogAnswer(object):
    """While active, every file dialog Maya/Qt could open returns `path`
    instead of showing up.

    WHY: Auto Setup keeps the chosen FBX in its own internal variable, set
    only by its Browse button. Typing into the text field changes what you
    SEE but not what it imports - which is why a changed FBX re-imported the
    old one. So we click the tool's own Browse button and answer its file
    dialog for it: its own code then stores the path exactly as it would
    for a real browse. `calls` tells us whether a dialog was really asked."""

    def __init__(self, path):
        self.path = path.replace("\\", "/")
        self.calls = 0
        self._saved = []

    def _answer(self, kind):
        def fake(*args, **kwargs):
            self.calls += 1
            if kind == "maya":
                return [self.path]
            if kind == "qt_file":
                return (self.path, "")
            return self.path                      # qt_dir
        return fake

    def _patch(self, owner, name, value):
        if owner is not None and hasattr(owner, name):
            self._saved.append((owner, name, getattr(owner, name)))
            setattr(owner, name, value)

    def __enter__(self):
        import maya.cmds as mc
        self._patch(mc, "fileDialog2", self._answer("maya"))
        for mod in ("pymel.core", "pymel.core.system"):
            self._patch(sys.modules.get(mod), "fileDialog2", self._answer("maya"))
        qfd = QtWidgets.QFileDialog
        self._patch(qfd, "getOpenFileName", staticmethod(self._answer("qt_file")))
        self._patch(qfd, "getSaveFileName", staticmethod(self._answer("qt_file")))
        self._patch(qfd, "getExistingDirectory", staticmethod(self._answer("qt_dir")))
        return self

    def __exit__(self, *exc):
        for owner, name, value in reversed(self._saved):
            try:
                setattr(owner, name, value)
            except Exception:
                pass


def _row_button(page, edit):
    """The (icon-only) browse button on the same row as `edit`, to its right."""
    e_top = edit.mapTo(page, QtCore.QPoint(0, 0))
    e_mid = e_top.y() + edit.height() // 2
    best = None
    for b in page.findChildren(QtWidgets.QAbstractButton):
        if not b.isVisible() or _btn_text(b) == TEXT_IMPORT_BTN:
            continue
        top = b.mapTo(page, QtCore.QPoint(0, 0))
        if top.y() <= e_mid <= top.y() + b.height() and top.x() >= e_top.x() + edit.width() - 5:
            if best is None or top.x() < best.mapTo(page, QtCore.QPoint(0, 0)).x():
                best = b
    return best


def _set_path_via_browse(page, edit, path, label):
    """Set one path the way a user browse does (see _FileDialogAnswer)."""
    btn = _row_button(page, edit)
    if btn is None:
        raise RuntimeError("No browse button found next to the {} field. "
                           "Run cc.inspect_ui() and send the output.".format(label))
    with _FileDialogAnswer(path) as answer:
        btn.click()
        _pump(0.3)
    if not answer.calls:
        raise RuntimeError("The {} browse button did not ask for a file the way this script "
                           "expects - send the output of cc.inspect_ui().".format(label))
    shown = edit.text().replace("\\", "/").lower()
    if shown != path.replace("\\", "/").lower():
        cmds.warning("[ssd_cc_autosetup] {} field shows {!r} after browse, expected {!r}".format(
            label, edit.text(), path))


def import_character(tabs, fbx, json_path=None, timeout=600):
    """Import tab: fill FBX/JSON fields, click Import, wait for the new root joint."""
    idx, page = _tab_page(tabs, TEXT_IMPORT_TAB)
    tabs.setCurrentIndex(idx)
    _pump()

    # Visible line edits on the Import page, top to bottom: FBX, JSON, textures.
    edits = [e for e in page.findChildren(QtWidgets.QLineEdit) if e.isVisible()]
    edits.sort(key=lambda e: e.mapTo(page, QtCore.QPoint(0, 0)).y())
    if len(edits) < 2:
        raise RuntimeError("Expected FBX and JSON fields on the Import tab, found {}. "
                           "Run cc.inspect_ui() and send the output.".format(len(edits)))

    _set_path_via_browse(page, edits[0], fbx, "FBX")
    if json_path:
        _set_path_via_browse(page, edits[1], json_path, "JSON")

    btn = _find_button(page, TEXT_IMPORT_BTN)
    if btn is None:
        raise RuntimeError("No '{}' button on the Import tab".format(TEXT_IMPORT_BTN))
    _wait_for(btn.isEnabled, 5, "the Import button to become enabled (are the paths valid?)")

    before = _cc_roots()
    _log("importing " + fbx)
    btn.click()
    new_roots = _wait_for(lambda: sorted(_cc_roots() - before), timeout,
                          "a new {} joint after import".format(ROOT_JOINT))
    _pump(1.0)      # let the tool finish its post-import material/UI work
    # Safety net: the FBX importer puts the character in a namespace named
    # after the file, so a different name means the wrong file came in.
    stem = os.path.splitext(os.path.basename(fbx))[0].lower()
    ns = new_roots[0].split("|")[-1].rpartition(":")[0].split(":")[-1].lower()
    if ns and not ns.startswith(stem):
        cmds.warning("[ssd_cc_autosetup] imported namespace '{}' does not match the FBX "
                     "name '{}' - check the right file was imported!".format(ns, stem))
    return new_roots[0]


def generate_face_rig(tabs, root, timeout=30):
    """Select the character, open the Face Rig tab and click Generate Face Rig."""
    cmds.select(root, replace=True)
    _pump(0.5)      # the tool listens to selection changes (scriptJob)
    idx, page = _tab_page(tabs, TEXT_FACE_TAB)
    _wait_for(lambda: tabs.isTabEnabled(idx), timeout, "the Face Rig tab to become enabled")
    tabs.setCurrentIndex(idx)
    _pump(0.5)
    btn = _wait_for(lambda: (_find_button(page, TEXT_FACE_BTN)
                             if _find_button(page, TEXT_FACE_BTN) and _find_button(page, TEXT_FACE_BTN).isEnabled()
                             else None),
                    timeout, "the '{}' button".format(TEXT_FACE_BTN))
    _log("generating face rig on " + root)
    btn.click()
    _pump(1.0)


def run(fbx, json_path=None, face_rig=True, auto_close_popups=True):
    """One call: import `fbx` through Auto Setup and build the face rig.

    json_path: defaults to <same folder>/<same name>.json if that exists.
    Returns the long name of the new root joint."""
    fbx = os.path.normpath(fbx)
    if not os.path.isfile(fbx):
        raise IOError("FBX not found: " + fbx)
    if json_path is None:
        guess = os.path.splitext(fbx)[0] + ".json"
        json_path = guess if os.path.isfile(guess) else ""
        if not json_path:
            cmds.warning("[ssd_cc_autosetup] No JSON next to the FBX - importing without it.")

    closer = _PopupCloser() if auto_close_popups else None
    if closer:
        closer.start()
    try:
        tabs = open_ui()
        root = import_character(tabs, fbx, json_path)
        _log("new character root: " + root)
        if face_rig:
            generate_face_rig(tabs, root)
    finally:
        if closer:
            closer.stop()
    _log("done: " + os.path.basename(fbx))
    return root


def run_many(fbx_files, save=True, out_dir=None, **kwargs):
    """Batch: each FBX in a NEW scene; with save=True writes <name>_autosetup.ma
    next to the FBX (or into out_dir). Keeps going if one file fails."""
    results = {}
    for fbx in fbx_files:
        try:
            cmds.file(new=True, force=True)
            root = run(fbx, **kwargs)
            if save:
                folder = out_dir or os.path.dirname(fbx)
                name = os.path.splitext(os.path.basename(fbx))[0] + "_autosetup.ma"
                path = os.path.join(folder, name).replace("\\", "/")
                cmds.file(rename=path)
                cmds.file(save=True, type="mayaAscii", force=True)
                _log("saved " + path)
            results[fbx] = root
        except Exception as e:
            cmds.warning("[ssd_cc_autosetup] FAILED {}: {}".format(fbx, e))
            results[fbx] = None
    ok = sum(1 for v in results.values() if v)
    _log("batch finished: {}/{} succeeded".format(ok, len(results)))
    return results


def inspect_ui():
    """Print the Auto Setup window's tabs, fields and buttons - send this
    output if run() can't find something."""
    tabs = open_ui()
    for i in range(tabs.count()):
        page = tabs.widget(i)
        print("TAB {} '{}' enabled={}".format(i, tabs.tabText(i), tabs.isTabEnabled(i)))
        for e in page.findChildren(QtWidgets.QLineEdit):
            print("   LineEdit  name={!r} visible={} text={!r}".format(e.objectName(), e.isVisible(), e.text()))
        for b in page.findChildren(QtWidgets.QAbstractButton):
            if _btn_text(b):
                print("   {:<10} name={!r} enabled={} text={!r}".format(
                    type(b).__name__, b.objectName(), b.isEnabled(), _btn_text(b)))
