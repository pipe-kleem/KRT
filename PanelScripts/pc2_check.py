# -*- coding: utf-8 -*-
"""PC2 check - the 'CHECK PC2 IN BLENDER' button (after Publish).

At the end of a rig the artist wants to know: does the rig's PC2 export work in Blender?
  1. reads the mesh names of the Blender File of the 'Import 3D + LOD Organize (Blender)' panel (headless Blender)
  2. loads the test animation (Playblast tab .anim) on the rig controls of the CURRENT Maya scene
  3. exports PC2 (same method as the studio cache exporter) for the Maya meshes that exist in that Blender file
  4. undoes the test animation, then, as the artist chose:
       * Blender file : opens a TEMPORARY COPY of the .blend in a normal Blender window with the PC2 applied by the pipeline
                        tool's own code, timeline set to the range and visible - the artist scrubs it by hand
       * Render       : renders a quick preview sequence in background Blender and plays it in a Maya window
       * Both
  5. temp copies / PC2 files / preview frames are deleted when Blender / the window is closed.
The server .blend is only read (copied) - never opened for writing. Any error is shown in a window you can copy and send.
"""
import os
import re
import sys
import json
import time
import uuid
import glob
import shutil
import tempfile
import threading
import traceback
import subprocess

import maya.cmds as cmds
import maya.mel as mel

try:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
import maya.OpenMayaUI as omui

_HERE = os.path.dirname(os.path.abspath(__file__))
_BLENDER_SCRIPT = os.path.join(_HERE, "blend_abc_tool", "pc2_blender.py")
_VIEWERS = []


def _log(msg):
    sys.stdout.write("[KRT PC2] " + msg + "\n")


def _main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


def _info(title, text):
    cmds.confirmDialog(title=title, message=text, button=["OK"], defaultButton="OK", dismissString="OK")


def _error_dialog(title, text):
    """Error window with the full text selectable + a Copy button, so the artist can send it."""
    dlg = QtWidgets.QDialog(_main_window())
    dlg.setWindowTitle(title)
    dlg.resize(760, 460)
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.addWidget(QtWidgets.QLabel("Something went wrong. Press 'Copy' and send this text:"))
    box = QtWidgets.QPlainTextEdit(text)
    box.setReadOnly(True)
    box.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
    lay.addWidget(box, 1)
    row = QtWidgets.QHBoxLayout()
    cp = QtWidgets.QPushButton("Copy to clipboard")
    ok = QtWidgets.QPushButton("Close")
    row.addStretch()
    row.addWidget(cp)
    row.addWidget(ok)
    lay.addLayout(row)
    cp.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(text))
    ok.clicked.connect(dlg.accept)
    try:
        dlg.exec()
    except AttributeError:
        dlg.exec_()


class _Progress(object):
    """Maya progress window: shows what is happening; ESC cancels."""
    def __init__(self, title="KRT - Check PC2 in Blender"):
        self._open = True
        cmds.progressWindow(title=title, progress=0, status="Starting ...", isInterruptable=True, maxValue=100)

    def update(self, pct, text):
        if self._open:
            cmds.progressWindow(edit=True, progress=int(pct), status=text)
        _log("%3d%%  %s" % (pct, text))
        QtWidgets.QApplication.processEvents()

    def cancelled(self):
        return self._open and bool(cmds.progressWindow(query=True, isCancelled=True))

    def close(self):
        if self._open:
            self._open = False
            cmds.progressWindow(endProgress=True)


class _Cancelled(Exception):
    pass


def glob_dirs(pattern):
    return [p for p in glob.glob(pattern) if os.path.isdir(p)]


def _find_blender():
    """Prefer the Blender version that has the pipeline addon (ssd_loader) installed; else the usual finder."""
    roaming = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
    folders = sorted(glob_dirs(r"C:/blender/blender*") + glob_dirs(r"C:/Program Files/Blender Foundation/Blender*"))
    best = None
    for f in folders:
        exe = os.path.join(f, "blender.exe")
        if not os.path.isfile(exe):
            continue
        m = re.search(r"(\d+\.\d+)", os.path.basename(f))
        if m and os.path.isfile(os.path.join(roaming, m.group(1), "scripts", "addons", "ssd_loader.py")):
            best = exe
    if best:
        return best
    tool = os.path.join(_HERE, "blend_abc_tool")
    if tool not in sys.path:
        sys.path.insert(0, tool)
    import maya_side
    return maya_side.find_blender("")


def _short(name):
    return name.split("|")[-1].split(":")[-1]


def _clean(name):
    return _short(name).strip().lower().split(".")[0]


def _blend_mesh_names(blender, blend, prog=None):
    """Names of all mesh objects in the .blend (headless Blender, read only)."""
    out = os.path.join(tempfile.gettempdir(), "krt_pc2_names_%s.json" % uuid.uuid4().hex[:6])
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
    proc = subprocess.Popen([blender, "-b", "--factory-startup", blend, "--python", _BLENDER_SCRIPT, "--", "names", out],
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, **kw)
    t0 = time.time()
    while proc.poll() is None:
        if prog is not None:
            prog.update(min(14, 3 + (time.time() - t0) * 0.5),
                        "Reading mesh names from the .blend (Blender, background) ... %ds" % (time.time() - t0))
            if prog.cancelled():
                proc.kill()
                raise _Cancelled()
        if time.time() - t0 > 600:
            proc.kill()
            break
        time.sleep(0.15)
    if not os.path.isfile(out):
        raise RuntimeError("Blender did not write the mesh names (exit code %s). Blender: %s\nFile: %s" % (
            proc.returncode, blender, blend))
    try:
        with open(out) as f:
            return json.load(f)
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def _matching_meshes(blend_names):
    """Maya mesh transforms whose name matches a mesh of the Blender file (same rule as the pipeline tool)."""
    wanted = {}
    for n in blend_names:
        wanted[_clean(n)] = n
    found, seen = [], {}
    for shape in cmds.ls(type="mesh", long=True, noIntermediate=True) or []:
        par = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        if not par:
            continue
        t = par[0]
        c = _clean(t)
        hit = c in wanted or (c.startswith("geo_") and c[4:] in wanted) or ("geo_" + c) in wanted
        if hit and t not in seen:
            seen[t] = True
            found.append(t)
    return found


def _export_pc2(transforms, out_dir, start, end, prog=None):
    """cacheFile OneFile -> .mcx -> .pc2 per mesh, same method as the studio Cache Exporter. -> (ok, errors)"""
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "_tmp_mcx_%s" % uuid.uuid4().hex[:6])
    os.makedirs(tmp)
    safe = tmp.replace("\\", "/").rstrip("/") + "/"
    cache_name = "pc2check"
    shapes, owners = [], []
    for t in sorted(transforms):
        for s in cmds.listRelatives(t, shapes=True, type="mesh", fullPath=True, noIntermediate=True) or []:
            shapes.append(s)
            owners.append(t)
    ok, errors = [], []
    if not shapes:
        return ok, [("cacheFile", "no mesh shapes")]
    sel, t0 = cmds.ls(selection=True, long=True) or [], cmds.currentTime(q=True)
    if prog:
        prog.update(40, "Recording %d meshes, frames %d-%d (Maya cache) ... this is the slow part" % (len(shapes), start, end))
    try:
        cmds.cacheFile(format="OneFile", directory=safe, fileName=cache_name, startTime=int(start), endTime=int(end),
                       sampleMultiplier=1, worldSpace=1, points=shapes)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return ok, [("cacheFile", str(e))]
    finally:
        cmds.currentTime(t0, edit=True, update=True)
        if sel:
            cmds.select(sel, replace=True)
        else:
            cmds.select(clear=True)
    used = set()
    for idx, t in enumerate(owners):
        if prog:
            prog.update(70 + 25.0 * idx / max(1, len(owners)), "Writing PC2 %d/%d: %s" % (idx + 1, len(owners), _short(t)))
            if prog.cancelled():
                shutil.rmtree(tmp, ignore_errors=True)
                raise _Cancelled()
        base = cache_name + ("" if idx == 0 else str(idx))
        name = _short(t)
        if not os.path.exists(os.path.join(tmp, base + ".mcx")):
            errors.append((name, "mcx not written"))
            continue
        if name.lower() in used:
            errors.append((name, "duplicate mesh name - skipped"))
            continue
        used.add(name.lower())
        try:
            mel.eval('cacheFile -pc2 0 -pcf "%s" -f "%s" -dir "%s"' % (safe + base + ".pc2", base, safe))
            shutil.copy2(safe + base + ".pc2", os.path.join(out_dir, name + ".pc2"))
            ok.append(name)
        except Exception as e:
            errors.append((name, str(e)))
    shutil.rmtree(tmp, ignore_errors=True)
    return ok, errors


# ── render preview ───────────────────────────────────────────────────────────
class _FrameViewer(QtWidgets.QDialog):
    """Plays the rendered preview frames; slider to scrub. Frames are deleted when it is closed."""
    def __init__(self, folder, frames):
        super(_FrameViewer, self).__init__(_main_window())
        self._folder, self._frames, self._i = folder, frames, 0
        self.setWindowTitle("PC2 render preview (temporary)")
        self.resize(980, 640)
        lay = QtWidgets.QVBoxLayout(self)
        self.img = QtWidgets.QLabel()
        self.img.setAlignment(QtCore.Qt.AlignCenter)
        self.img.setMinimumSize(640, 360)
        lay.addWidget(self.img, 1)
        row = QtWidgets.QHBoxLayout()
        self.btn = QtWidgets.QPushButton("Pause")
        self.lbl = QtWidgets.QLabel("")
        self.sl = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl.setRange(0, len(frames) - 1)
        row.addWidget(self.btn)
        row.addWidget(self.sl, 1)
        row.addWidget(self.lbl)
        lay.addLayout(row)
        close = QtWidgets.QPushButton("Close (deletes the preview frames)")
        lay.addWidget(close)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.btn.clicked.connect(self._toggle)
        self.sl.valueChanged.connect(self._show)
        close.clicked.connect(self.close)
        self.timer.start(80)
        self._show(0)

    def _toggle(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn.setText("Play")
        else:
            self.timer.start(80)
            self.btn.setText("Pause")

    def _tick(self):
        self.sl.setValue((self._i + 1) % len(self._frames))

    def _show(self, i):
        self._i = int(i)
        pm = QtGui.QPixmap(self._frames[self._i])
        self.img.setPixmap(pm.scaled(self.img.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        m = re.search(r"(\d+)\.png$", self._frames[self._i])
        self.lbl.setText("frame %s   (%d/%d)" % (m.group(1) if m else "?", self._i + 1, len(self._frames)))

    def resizeEvent(self, e):
        super(_FrameViewer, self).resizeEvent(e)
        if self._frames:
            self._show(self._i)

    def closeEvent(self, e):
        self.timer.stop()
        shutil.rmtree(self._folder, ignore_errors=True)
        super(_FrameViewer, self).closeEvent(e)


def _render_preview(blender, blend_copy, pc2_dir, start, end, prog):
    """Background Blender renders a quick sequence; returns the frame folder (outside the work folder)."""
    out_dir = tempfile.mkdtemp(prefix="krt_pc2_render_")
    n_total = end - start + 1
    step = max(1, int(round(n_total / 48.0)))
    expected = len(range(start, end + 1, step)) + (0 if (end - start) % step == 0 else 1)
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
    log_path = os.path.join(out_dir, "_blender.log")
    logf = open(log_path, "w")
    proc = subprocess.Popen([blender, "-b", blend_copy, "--python", _BLENDER_SCRIPT, "--", "render", pc2_dir,
                             str(start), str(end), out_dir, str(step)], stdout=logf, stderr=subprocess.STDOUT, **kw)
    t0 = time.time()
    while proc.poll() is None:
        done = len(glob.glob(os.path.join(out_dir, "frame_*.png")))
        prog.update(min(97, 5 + 90.0 * done / max(1, expected)),
                    "Rendering preview frame %d/%d (Blender, background) ... %ds" % (done, expected, time.time() - t0))
        if prog.cancelled():
            proc.kill()
            logf.close()
            shutil.rmtree(out_dir, ignore_errors=True)
            raise _Cancelled()
        time.sleep(0.3)
    logf.close()
    frames = sorted(glob.glob(os.path.join(out_dir, "frame_*.png")))
    if not frames:
        try:
            with open(log_path) as f:
                tail = "".join(f.readlines()[-25:])
        except OSError:
            tail = ""
        shutil.rmtree(out_dir, ignore_errors=True)
        raise RuntimeError("Blender rendered no frames (exit code %s). Last Blender output:\n%s" % (proc.returncode, tail))
    return out_dir, frames


# ── main entry ───────────────────────────────────────────────────────────────
def run(ws, blend_path):
    """ws = the SessionWorkspace (has the Playblast tab fields). blend_path = the Blender File of the Blender panel."""
    try:
        _run(ws, blend_path)
    except _Cancelled:
        cmds.warning("[KRT] PC2 check cancelled.")
    except Exception:
        try:
            cmds.progressWindow(endProgress=True)
        except Exception:
            pass
        tb = traceback.format_exc()
        sys.stdout.write(tb + "\n")
        _error_dialog("KRT - Check PC2 in Blender - ERROR", "KRT %s\nBlender file: %s\n\n%s" % (
            _krt_version(), blend_path, tb))


def _krt_version():
    try:
        from .. import __version__
        return __version__
    except Exception:
        return "?"


def _run(ws, blend_path):
    if not blend_path or not os.path.isfile(blend_path):
        _info("KRT - PC2 check", "Blender File not found:\n%s\n\nSet it in the 'Import 3D + LOD Organize (Blender)' panel first." % blend_path)
        return
    if not os.path.isfile(_BLENDER_SCRIPT):
        _info("KRT - PC2 check", "pc2_blender.py is missing:\n" + _BLENDER_SCRIPT)
        return

    anim = (ws.pb_anim_field.text() or "").strip() if hasattr(ws, "pb_anim_field") else ""
    pattern = (ws.pb_pattern_field.text() or "*_ctl").strip() if hasattr(ws, "pb_pattern_field") else "*_ctl"
    ask = ("Check PC2 in Blender\n\nBlender file:\n%s\n\n" % blend_path +
           ("The test animation (%s) is loaded on the rig controls (%s) of this scene, PC2 is exported, and the "
            "animation is undone afterwards." % (os.path.basename(anim), pattern) if anim else
            "No .anim set in the Playblast tab - the scene's current animation / timeline is exported as it is.") +
           "\n\nWhat do you want to see?")
    choice = cmds.confirmDialog(title="KRT - Check PC2 in Blender", message=ask,
                                button=["Blender file", "Render", "Both", "Cancel"], defaultButton="Blender file",
                                cancelButton="Cancel", dismissString="Cancel")
    if choice == "Cancel":
        return
    want_blender = choice in ("Blender file", "Both")
    want_render = choice in ("Render", "Both")

    work = tempfile.mkdtemp(prefix="krt_pc2_check_")
    pc2_dir = os.path.join(work, "pc2")
    blend_copy = os.path.join(work, os.path.basename(blend_path))
    prog = _Progress()
    undo_open = False
    ok, errors, start, end, blender = [], [], 0, 0, ""
    try:
        prog.update(2, "Looking for Blender ...")
        blender = _find_blender()
        _log("Blender: " + blender)
        names = _blend_mesh_names(blender, blend_path, prog)
        prog.update(15, "Matching Maya meshes with the %d meshes of the Blender file ..." % len(names))
        meshes = _matching_meshes(names)
        if not meshes:
            prog.close()
            _info("KRT - PC2 check", "None of the Maya meshes in this scene match the %d meshes of the Blender file.\n\n"
                  "Blender examples: %s\n\nOpen the rig scene first (the meshes must have the same names)." % (
                      len(names), ", ".join(names[:5])))
            shutil.rmtree(work, ignore_errors=True)
            return
        _log("%d Maya meshes match the Blender file (%d meshes there)." % (len(meshes), len(names)))

        try:
            start = int(ws.pb_start_field.text())
            end = int(ws.pb_end_field.text())
        except Exception:
            start = int(cmds.playbackOptions(q=True, minTime=True))
            end = int(cmds.playbackOptions(q=True, maxTime=True))

        cmds.undoInfo(openChunk=True)
        undo_open = True
        if anim:
            prog.update(20, "Loading the test animation on the rig controls (%s) ..." % pattern)
            okl, err, n = ws.pb_load_anim_on_filtered_controls(anim, pattern)
            if not okl:
                raise RuntimeError("Could not load the test animation:\n%s" % err)
            prog.update(35, "Animation loaded on %d controls." % n)
            if prog.cancelled():
                raise _Cancelled()

        ok, errors = _export_pc2(meshes, pc2_dir, start, end, prog)
    except BaseException:
        prog.close()
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        if undo_open:
            cmds.undoInfo(closeChunk=True)
            try:
                if anim:
                    cmds.undo()         # remove the test animation again
            except Exception:
                pass
    if not ok:
        prog.close()
        _error_dialog("KRT - PC2 check", "No PC2 file was written.\n\n" + "\n".join("%s: %s" % e for e in errors[:40]))
        shutil.rmtree(work, ignore_errors=True)
        return

    prog.update(97, "Copying the .blend (temporary copy) ...")
    shutil.copy2(blend_path, blend_copy)          # temporary COPY - the server file is only read

    frames_dir, frames = "", []
    if want_render:
        try:
            frames_dir, frames = _render_preview(blender, blend_copy, pc2_dir, start, end, prog)
        except _Cancelled:
            prog.close()
            shutil.rmtree(work, ignore_errors=True)
            raise
        except Exception:
            prog.close()
            _error_dialog("KRT - PC2 render failed", traceback.format_exc())
            if not want_blender:
                shutil.rmtree(work, ignore_errors=True)
                return
    prog.update(100, "Done." if not want_blender else "Opening Blender - PC2 is applied when it is up ...")
    prog.close()

    if want_blender:
        proc = subprocess.Popen([blender, blend_copy, "--python", _BLENDER_SCRIPT, "--", "apply", pc2_dir, str(start), str(end)])

        def _cleanup():
            proc.wait()
            shutil.rmtree(work, ignore_errors=True)
        threading.Thread(target=_cleanup, daemon=True).start()
    else:
        shutil.rmtree(work, ignore_errors=True)

    if frames:
        v = _FrameViewer(frames_dir, frames)
        _VIEWERS.append(v)
        v.show()

    msg = "%d PC2 file(s) exported (frames %d-%d)." % (len(ok), start, end)
    if want_blender:
        msg += ("\n\nBlender is opening a temporary copy of the file with PC2 applied. The timeline is set to %d-%d - "
                "drag the playhead to check. A message in Blender tells how many meshes got a cache."
                % (start, end))
    if frames:
        msg += "\n\nThe render preview is in its own window."
    if errors:
        msg += "\n\n%d problem(s):\n%s" % (len(errors), "\n".join("  %s: %s" % e for e in errors[:10]))
    msg += "\n\nTemporary files are deleted when you close Blender / the preview. Do not save over the server file."
    _info("KRT - PC2 check", msg)
