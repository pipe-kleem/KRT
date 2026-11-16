# -*- coding: utf-8 -*-
"""
maya_side.py - helpers used by run_in_maya.py
  * find Blender
  * run Blender headless (finalise + clean export)
  * import the resulting ABC into Maya
"""
import os
import sys
import re
import glob
import json
import time
import queue
import threading
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_ENTRY = os.path.join(HERE, "blender_run.py")


_T0 = [time.time()]


def log(msg):
    """Print to Maya's Script Editor output with a running time stamp."""
    sys.stdout.write("[blend->abc %6.1fs] %s\n" % (time.time() - _T0[0], msg))
    sys.stdout.flush()


def _pump_ui():
    """Let Maya redraw (Script Editor / progress bar) while we wait for Blender."""
    try:
        try:
            from PySide6 import QtWidgets
        except ImportError:
            from PySide2 import QtWidgets
        QtWidgets.QApplication.processEvents()
    except Exception:
        pass


class _Progress(object):
    """Maya progress window (ESC = cancel). Silently does nothing outside Maya."""
    def __init__(self, title):
        try:
            import maya.cmds as cmds
            self.cmds = cmds
            cmds.progressWindow(title=title, progress=0, status="Starting ...", isInterruptable=True,
                                maxValue=100)
        except Exception:
            self.cmds = None

    def update(self, pct, status):
        if self.cmds:
            try:
                self.cmds.progressWindow(edit=True, progress=int(pct), status=status[:90])
            except Exception:
                pass

    def cancelled(self):
        try:
            return bool(self.cmds and self.cmds.progressWindow(query=True, isCancelled=True))
        except Exception:
            return False

    def close(self):
        if self.cmds:
            try:
                self.cmds.progressWindow(endProgress=True)
            except Exception:
                pass


_NOISE = ("Fra:", "Saved:", "Blender 4.", "Blender 5.", "Read blend", "Warning: Unknown", "SSD_RESULT:")
_STAGE = (("[blend]", 5, "Blend file opened"),
          ("[finalise] running", 10, "Finalise File ..."),
          ("[finalise]", 20, "Finalise done"),
          ("[export] ", 25, "Exporting Alembic ..."),
          ("[playblast] starting", 45, "Wrinkle playblast ..."))
_PB = re.compile(r"\[playblast\] \((\d+)/(\d+)\)")


LAST_RESULT = {}      # the status dict printed by blender_run.py (SSD_RESULT:...) of the last export


def _stream_blender(cmd, timeout):
    """Run Blender, print every useful output line LIVE in Maya, keep a progress bar.
    Returns (returncode, all_output_lines)."""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000   # CREATE_NO_WINDOW
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            universal_newlines=True, bufsize=1, env=env, **kwargs)
    q = queue.Queue()

    def reader():
        for line in iter(proc.stdout.readline, ""):
            q.put(line.rstrip("\r\n"))
        q.put(None)
    threading.Thread(target=reader, daemon=True).start()

    prog = _Progress("Blender -> ABC")
    lines, start, done = [], time.time(), False
    try:
        while not done:
            try:
                line = q.get(timeout=0.1)
            except queue.Empty:
                line = ""
            if line is None:
                done = True
            elif line:
                lines.append(line)
                if "CYCLESHAIR" in line or line.startswith(_NOISE):
                    pass                                   # harmless / very chatty Blender lines
                else:
                    log("  | " + line)
                    for key, pct, text in _STAGE:
                        if line.startswith(key):
                            prog.update(pct, text)
                            break
                    m = _PB.match(line)
                    if m:
                        i, n = int(m.group(1)), max(int(m.group(2)), 1)
                        prog.update(45 + 50.0 * i / n, "Wrinkle playblast %d/%d" % (i, n))
            _pump_ui()
            if prog.cancelled():
                proc.kill()
                raise RuntimeError("Cancelled by user (ESC) - Blender stopped.")
            if timeout and time.time() - start > timeout:
                proc.kill()
                raise RuntimeError("Blender timed out after %s s." % timeout)
        proc.wait()
    finally:
        prog.close()
    return proc.returncode, lines


def find_blender(blender_exe=""):
    if blender_exe and os.path.isfile(blender_exe):
        return blender_exe
    found = []
    for pat in (r"C:/blender/blender*/blender.exe",
                r"C:/Blender/blender*/blender.exe",
                r"C:/Program Files/Blender Foundation/Blender*/blender.exe",
                r"C:/Program Files (x86)/Blender Foundation/Blender*/blender.exe",
                r"D:/Program Files/Blender Foundation/Blender*/blender.exe"):
        found.extend(glob.glob(pat))
    if not found:
        raise RuntimeError("Blender not found. Set BLENDER_EXE in run_in_maya.py.")
    return sorted(found)[-1]


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def _is_inside(path, root):
    path, root = _norm(path), _norm(root)
    return path == root or path.startswith(root.rstrip("\\/") + os.sep)


def unique_abc_path(path):
    """name.abc -> if it exists: name_v002.abc, name_v003.abc ... (never overwrites)."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while True:
        cand = "%s_v%03d%s" % (base, n, ext)
        if not os.path.exists(cand):
            return cand
        n += 1


_VER = re.compile(r"_v(\d+)", re.IGNORECASE)


def latest_folder_version(folder):
    """Highest '_vNN' number found in the .abc file names of `folder` (0 if none).
    e.g. workfileMaster_model_v16.abc -> 16 ; KL_x_v01_v017.abc -> 17 (last _v group counts)."""
    best = 0
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    for n in names:
        if n.lower().endswith(".abc"):
            nums = _VER.findall(n[:-4])
            if nums:
                best = max(best, int(nums[-1]))
    return best


def resolve_abc_path(blend_path, output_dir, abc_name="", forbidden_roots=(),
                     version_from_folder=True):
    """Work out the .abc path.
    output_dir : the folder to save into (or a full path ending in .abc). Required.
    Name = <blend name, keeping its own version>  +  OUR version:
        version_from_folder=True : _v<latest version in the folder + 1>   (e.g. ..._v01_v017.abc)
        version_from_folder=False: no suffix, but _v002, _v003 ... if the name already exists
    Never overwrites. REFUSED: next to the source .blend, and under a forbidden root."""
    if not output_dir:
        raise ValueError("OUTPUT_DIR is empty. Set the folder to save the ABC into in run_in_maya.py.")
    out = os.path.abspath(output_dir)
    stem = os.path.splitext(os.path.basename(blend_path))[0]
    if abc_name:
        stem = os.path.splitext(os.path.basename(abc_name))[0]       # "name" or "name.abc"
    if out.lower().endswith(".abc"):
        abc_path = out if not abc_name else os.path.join(os.path.dirname(out), stem + ".abc")
    else:
        folder = out
        if version_from_folder:
            latest = latest_folder_version(folder)
            log("Output folder latest version: %s -> new ABC version v%03d" %
                ("v%02d" % latest if latest else "none", latest + 1))
            stem = "%s_v%03d" % (stem, latest + 1)
        abc_path = os.path.join(folder, stem + ".abc")

    target = os.path.dirname(abc_path)
    if _is_inside(target, os.path.dirname(os.path.abspath(blend_path))):
        raise ValueError("Refusing to write next to the source .blend (server folder):\n  " + abc_path)
    for root in forbidden_roots:
        if root and _is_inside(target, root):
            raise ValueError("Refusing to write under protected location %s:\n  %s" % (root, abc_path))
    return unique_abc_path(abc_path)


def export_blend_to_abc(blend_path, output_dir, blender_exe="",
                        options=None, timeout=1800, abc_name="",
                        playblast_dir="", playblast_options=None, forbidden_roots=(),
                        version_from_folder=True):
    """Run headless Blender on one .blend. Returns the exported .abc path.
    The .blend is never saved; the ABC / playblast frames are only written to the local
    paths given (checked by resolve_abc_path)."""
    blend_path = os.path.abspath(blend_path)
    if not os.path.isfile(blend_path):
        raise IOError("Blend file not found: " + blend_path)
    if not os.path.isfile(BLENDER_ENTRY):
        raise IOError("blender_run.py not found next to maya_side.py: " + BLENDER_ENTRY)

    abc_path = resolve_abc_path(blend_path, output_dir, abc_name, forbidden_roots,
                                version_from_folder)
    if playblast_dir:
        for root in [os.path.dirname(blend_path)] + list(forbidden_roots):
            if root and _is_inside(playblast_dir, root):
                raise ValueError("Playblast temp folder is on the server: " + playblast_dir)

    cmd = [
        find_blender(blender_exe), "-b", "--factory-startup", "--python-exit-code", "1",
        blend_path, "--python", BLENDER_ENTRY, "--",
        "--out", abc_path,
        "--options", json.dumps(options) if options else "",
    ]
    if playblast_dir:
        cmd += ["--playblast-dir", playblast_dir,
                "--pb-options", json.dumps(playblast_options) if playblast_options else ""]
    _T0[0] = time.time()
    log("=" * 60)
    log("Blend file : " + blend_path)
    log("Blender    : " + cmd[0])
    log("ABC output : " + abc_path)
    log("Playblast  : " + ("wrinkle check ON" if playblast_dir else "off"))
    log("Starting Blender in the background (ESC in the progress window cancels) ...")

    returncode, lines = _stream_blender(cmd, timeout)
    LAST_RESULT.clear()
    for _ln in reversed(lines):
        if _ln.startswith("SSD_RESULT:"):
            try:
                LAST_RESULT.update(json.loads(_ln[len("SSD_RESULT:"):]))
            except Exception:
                pass
            break

    if returncode != 0 or not os.path.isfile(abc_path):
        tail = "\n".join(lines[-25:])
        raise RuntimeError("Blender export failed (exit %s). Last output:\n%s" % (returncode, tail))

    log("Blender finished OK (%.0f s)." % (time.time() - _T0[0]))
    log("Exported: " + abc_path)
    return abc_path


def import_abc_into_maya(abc_path):
    import maya.cmds as cmds
    if not cmds.pluginInfo("AbcImport", q=True, loaded=True):
        cmds.loadPlugin("AbcImport")
    log("Importing ABC into the Maya scene ...")
    before = set(cmds.ls(assemblies=True))
    cmds.AbcImport(abc_path, mode="import")
    new_nodes = [n for n in cmds.ls(assemblies=True) if n not in before]
    if new_nodes:
        cmds.select(new_nodes, replace=True)
    log("Imported into Maya: %s" % (", ".join(new_nodes) or "(no new top-level nodes)"))
    return new_nodes
