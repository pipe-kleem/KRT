# -*- coding: utf-8 -*-
"""
blender_run.py - entry point executed by headless Blender (launched from Maya):

    blender -b file.blend --python blender_run.py -- --out file.abc [--options JSON] [--save 1]
"""
import sys
import os
import json
import argparse
import traceback

# make sibling modules importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import blender_finalise
import blender_export


def main():
    try:                                   # flush every line so Maya can show progress live
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--options", default="")   # JSON, empty = all ON
    p.add_argument("--playblast-dir", default="")   # empty = no wrinkle playblast
    p.add_argument("--pb-options", default="")      # JSON overrides for blender_playblast.DEFAULTS
    args = p.parse_args(argv)

    opts = json.loads(args.options) if args.options else None

    status = {"ok": False}
    try:
        print("[blend] " + (bpy.data.filepath or "<unsaved>"))
        # Safety net: never write next to the source file (the .blend is NEVER saved by this script)
        src_dir = os.path.normcase(os.path.dirname(os.path.abspath(bpy.data.filepath))) if bpy.data.filepath else ""
        out_dir = os.path.normcase(os.path.dirname(os.path.abspath(args.out)))
        if src_dir and (out_dir == src_dir or out_dir.startswith(src_dir.rstrip("\\/") + os.sep)):
            raise RuntimeError("Refusing to write next to the source .blend: " + args.out)
        print("[finalise] running Finalise File (units, rename, modifiers, purge) ...")
        status["finalise"] = blender_finalise.finalise(opts)
        abc, n = blender_export.clean_export(args.out)
        status.update(ok=True, abc=abc, meshes=n)
        print("[export] %d meshes -> %s" % (n, abc))
    except Exception:
        status["error"] = traceback.format_exc()
        print(status["error"])

    # Wrinkle playblast runs LAST (it changes drivers/lights/visibility in memory only)
    # and can never make the ABC export fail.
    if status["ok"] and args.playblast_dir:
        try:
            import blender_playblast
            if blender_playblast.find_wrinkle_node()[1] is None:
                print("[playblast] no wrinkle maps in this model - playblast skipped")
                status["playblast_channels"] = 0
            else:
                pb = blender_playblast.make_wrinkle_playblast(
                    args.playblast_dir, json.loads(args.pb_options) if args.pb_options else None)
                status["playblast_channels"] = len(pb["channels"])
        except Exception:
            status["playblast_error"] = traceback.format_exc()
            print("[playblast] FAILED\n" + status["playblast_error"])

    print("SSD_RESULT:" + json.dumps(status))
    sys.stdout.flush()
    sys.exit(0 if status["ok"] else 1)


main()
