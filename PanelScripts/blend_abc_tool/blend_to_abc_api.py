# -*- coding: utf-8 -*-
"""
blend_to_abc_api.py - the function to call from ANOTHER TOOL (no config file, no globals).

    import sys
    sys.path.insert(0, r"<this folder>")          # or just keep the folder on sys.path
    import blend_to_abc_api

    abc, nodes = blend_to_abc_api.blend_to_abc(
        blend_path = r"P:\\...\\model_v01.blend",   # source .blend (read only, never saved)
        output_dir = r"D:\\my\\abc_folder",         # where the ABC is written (you choose)
        blender_exe = r"C:/blender/blender-4.5.3-windows-x64/blender.exe",   # "" = auto-detect
    )

Needs only the files in this folder + Blender. Must run inside Maya (it imports the ABC).
Use import_into_maya=False to only export (then it also works outside Maya).
See README.md for all options.
"""
import os
import sys
import shutil
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import maya_side

DEFAULT_FINALISE = {"units": True, "modifiers": True, "collections": True, "objects": True,
                    "materials": True, "purge_mats": True, "purge_all": True}


def _show_hidden_info(hidden):
    """Information popup (before the wrinkle window / import): meshes hidden in Blender were not exported.
    Continues when the artist presses OK."""
    if not hidden:
        return
    names = ["%s   (%s)" % (n, why) for n, why in hidden]
    shown = names[:40] + (["... and %d more" % (len(names) - 40)] if len(names) > 40 else [])
    text = ("%d mesh(es) are HIDDEN in the Blender file (eye / viewport button) and were NOT exported to the ABC:\n\n%s\n\n"
            "Press OK to continue." % (len(names), "\n".join(shown)))
    maya_side.log("HIDDEN meshes not exported: " + ", ".join(n for n, _w in hidden))
    try:
        import maya.cmds as cmds
        cmds.confirmDialog(title="KRT - Hidden meshes in Blender", message=text, button=["OK"],
                           defaultButton="OK", dismissString="OK")
    except Exception:
        pass


def blend_to_abc(blend_path, output_dir, blender_exe="", abc_name="",
                 wrinkle_playblast=True, import_into_maya=True,
                 finalise_options=None, playblast_options=None,
                 version_from_folder=True, forbidden_roots=(), timeout=1800,
                 playblast_fade=0.6, playblast_hold=0.25,
                 import_func=None, on_imported=None, on_rejected=None):
    """Finalise + Clean & Export ABC in background Blender, optional wrinkle check, Maya import.

    blend_path        : source .blend (never modified / saved)
    output_dir        : folder for the ABC (required; refused if next to the .blend or under
                        forbidden_roots)
    blender_exe       : path to blender.exe ("" = auto-detect)
    abc_name          : "" = blend file name; name gets our own _vNNN appended
    wrinkle_playblast : True = render a face wrinkle check; the artist judges it in a window
                        and the ABC is imported when they click OK. Models without wrinkle
                        maps skip it automatically. False = export (+ import) only.
    import_into_maya  : False = only export, return the .abc path
    Returns (abc_path, imported_maya_nodes). With the playblast window, nodes is [] because
    the import happens later, when the artist clicks OK.
    """
    opts = dict(DEFAULT_FINALISE)
    opts.update(finalise_options or {})
    pb_opts = dict(playblast_options or {})
    pb_opts.setdefault("ramp_steps", 1)
    pb_opts.setdefault("samples", 8)
    pb_opts.setdefault("resolution", 384)

    pb_dir = tempfile.mkdtemp(prefix="wrinkle_pb_") if wrinkle_playblast else ""
    try:
        abc = maya_side.export_blend_to_abc(
            blend_path, output_dir=output_dir, blender_exe=blender_exe, options=opts,
            timeout=timeout, abc_name=abc_name, playblast_dir=pb_dir,
            playblast_options=pb_opts, forbidden_roots=forbidden_roots,
            version_from_folder=version_from_folder)
    except Exception:
        if pb_dir:
            shutil.rmtree(pb_dir, ignore_errors=True)
        raise

    _show_hidden_info((getattr(maya_side, "LAST_RESULT", {}) or {}).get("hidden_meshes") or [])

    if pb_dir and not os.path.isfile(os.path.join(pb_dir, "manifest.json")):
        maya_side.log("No wrinkle playblast produced (no wrinkle maps) - importing directly.")
        shutil.rmtree(pb_dir, ignore_errors=True)
        pb_dir = ""

    # KRT integration: the ABC is only KEPT when it really gets imported.
    #  * on_imported(abc, nodes) is called after a successful Maya import
    #  * if the artist rejects the wrinkles (NOT OK / closes the window) the
    #    exported ABC is deleted again and on_rejected(abc) is called.
    def _delete_abc():
        try:
            os.remove(abc)
            maya_side.log("Not imported -> deleted the exported ABC: %s" % abc)
        except OSError as e:
            maya_side.log("Could not delete the ABC %s: %s" % (abc, e))

    def _import_now():
        n = import_func(abc) if import_func else maya_side.import_abc_into_maya(abc)
        if on_imported:
            on_imported(abc, n)
        return n

    def _rejected():
        _delete_abc()
        if on_rejected:
            on_rejected(abc)

    nodes = []
    if pb_dir:
        try:
            import maya_playblast_viewer
            maya_playblast_viewer.show(
                pb_dir, fade=playblast_fade, hold=playblast_hold,
                on_import=_import_now if import_into_maya else None,
                on_reject=_rejected if import_into_maya else None)
        except Exception:
            import traceback
            maya_side.log("!!! Wrinkle playblast window FAILED - details below")
            sys.stdout.write(traceback.format_exc() + "\n")
            shutil.rmtree(pb_dir, ignore_errors=True)       # frames are never needed
            if import_into_maya:
                nodes = _import_now()                       # don't block the artist
    elif import_into_maya:
        nodes = _import_now()
    return abc, nodes
