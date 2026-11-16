# -*- coding: utf-8 -*-
"""PC2 check - the 'CHECK PC2 IN BLENDER' button (after Publish).

At the end of a rig the artist wants to know: does the rig's PC2 export work in Blender?
  1. finds the Blender File of the 'Import 3D + LOD Organize (Blender)' panel and lists its mesh names (headless Blender)
  2. loads the test animation (Playblast tab .anim) on the rig controls of the CURRENT Maya scene
  3. exports PC2 (same method as the studio cache exporter) for the Maya meshes that exist in that Blender file
  4. opens a TEMPORARY COPY of the .blend in a normal Blender window and applies the PC2 caches with the pipeline tool's
     own code (Apply PC2 Caches & Rotate) - the artist checks it by hand
  5. when Blender is closed the temp copy and the PC2 files are deleted.
The server .blend is only read (copied) - never opened for writing. The test animation is undone in Maya afterwards.
"""
import os
import re
import sys
import json
import time
import uuid
import shutil
import tempfile
import threading
import subprocess

import maya.cmds as cmds
import maya.mel as mel

_HERE = os.path.dirname(os.path.abspath(__file__))
_BLENDER_SCRIPT = os.path.join(_HERE, "blend_abc_tool", "pc2_blender.py")


def _log(msg):
    sys.stdout.write("[KRT PC2] " + msg + "\n")


def _info(title, text):
    cmds.confirmDialog(title=title, message=text, button=["OK"], defaultButton="OK", dismissString="OK")


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


def glob_dirs(pattern):
    import glob
    return [p for p in glob.glob(pattern) if os.path.isdir(p)]


def _short(name):
    return name.split("|")[-1].split(":")[-1]


def _clean(name):
    return _short(name).strip().lower().split(".")[0]


def _blend_mesh_names(blender, blend):
    """Names of all mesh objects in the .blend (headless Blender, read only)."""
    out = os.path.join(tempfile.gettempdir(), "krt_pc2_names_%s.json" % uuid.uuid4().hex[:6])
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
    subprocess.run([blender, "-b", "--factory-startup", blend, "--python", _BLENDER_SCRIPT, "--", "names", out],
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600, **kw)
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
        if c.startswith("geo_"):
            c = c[4:]
        if c in wanted and t not in seen:
            seen[t] = True
            found.append(t)
    return found


def _export_pc2(transforms, out_dir, start, end):
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


def run(ws, blend_path):
    """ws = the SessionWorkspace (has the Playblast tab fields). blend_path = the Blender File of the Blender panel."""
    if not blend_path or not os.path.isfile(blend_path):
        _info("KRT - PC2 check", "Blender File not found:\n%s\n\nSet it in the 'Import 3D + LOD Organize (Blender)' panel first." % blend_path)
        return
    if not os.path.isfile(_BLENDER_SCRIPT):
        _info("KRT - PC2 check", "pc2_blender.py is missing:\n" + _BLENDER_SCRIPT)
        return

    anim = (ws.pb_anim_field.text() or "").strip() if hasattr(ws, "pb_anim_field") else ""
    pattern = (ws.pb_pattern_field.text() or "*_ctl").strip() if hasattr(ws, "pb_pattern_field") else "*_ctl"
    ask = ("Check PC2 in Blender?\n\nBlender file:\n%s\n\n" % blend_path +
           ("The test animation will be loaded on the rig controls (%s) of this scene, PC2 exported, and then the "
            "animation is undone.\n\nAnimation: %s" % (pattern, anim) if anim else
            "No .anim set in the Playblast tab - the scene's current animation / timeline is exported as it is."))
    if cmds.confirmDialog(title="KRT - Check PC2 in Blender", message=ask, button=["Start", "Cancel"],
                          defaultButton="Start", cancelButton="Cancel", dismissString="Cancel") != "Start":
        return

    work = tempfile.mkdtemp(prefix="krt_pc2_check_")
    pc2_dir = os.path.join(work, "pc2")
    blend_copy = os.path.join(work, os.path.basename(blend_path))
    cmds.waitCursor(state=True)
    undo_open = False
    try:
        blender = _find_blender()
        _log("Blender: " + blender)
        _log("Reading mesh names from the .blend ...")
        names = _blend_mesh_names(blender, blend_path)
        meshes = _matching_meshes(names)
        if not meshes:
            _info("KRT - PC2 check", "None of the Maya meshes in this scene match the %d meshes of the Blender file.\n"
                  "Open the rig scene first." % len(names))
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
            _log("Loading test animation on '%s' ..." % pattern)
            okl, err, n = ws.pb_load_anim_on_filtered_controls(anim, pattern)
            if not okl:
                cmds.undoInfo(closeChunk=True)
                undo_open = False
                cmds.undo()
                _info("KRT - PC2 check", "Could not load the test animation:\n%s" % err)
                shutil.rmtree(work, ignore_errors=True)
                return
            _log("Animation loaded on %d controls." % n)

        _log("Exporting PC2 %d-%d ..." % (start, end))
        ok, errors = _export_pc2(meshes, pc2_dir, start, end)
    finally:
        cmds.waitCursor(state=False)
        if undo_open:
            cmds.undoInfo(closeChunk=True)
            try:
                if anim:
                    cmds.undo()         # remove the test animation again
            except Exception:
                pass
    if not ok:
        _info("KRT - PC2 check", "No PC2 file was written.\n\n" + "\n".join("%s: %s" % e for e in errors[:15]))
        shutil.rmtree(work, ignore_errors=True)
        return

    shutil.copy2(blend_path, blend_copy)          # temporary COPY - the server file is only read
    cmd = [blender, blend_copy, "--python", _BLENDER_SCRIPT, "--", "apply", pc2_dir, str(start), str(end)]
    proc = subprocess.Popen(cmd)

    def _cleanup():
        proc.wait()
        shutil.rmtree(work, ignore_errors=True)
    threading.Thread(target=_cleanup, daemon=True).start()

    msg = "Blender is opening a temporary copy of the file with PC2 applied.\n\n%d PC2 exported (frames %d-%d)" % (
        len(ok), start, end)
    if errors:
        msg += "\n%d problem(s):\n%s" % (len(errors), "\n".join("  %s: %s" % e for e in errors[:10]))
    msg += ("\n\nCheck it by hand. When you close Blender the temporary copy and PC2 files are deleted "
            "(do not save over the server file).")
    _info("KRT - PC2 check", msg)
