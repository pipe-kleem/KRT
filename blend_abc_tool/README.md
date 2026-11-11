# Blend -> ABC -> Maya  (self-contained tool)

Give it a `.blend` path and an output folder. In the background (no Blender window) it:

1. runs **Finalise File** with every option ON (Set Scene Units, Hide Modifiers/Masks, Rename
   Collections / Objects / Materials, Purge Unused Mats, Purge ALL Unused Data),
2. runs **Clean & Export ABC** (visible meshes only),
3. optionally renders a quick **face wrinkle check** (blendshapes off, each wrinkle channel one by
   one) and shows it ONCE in a temporary Maya window,
4. imports the ABC into Maya (when the artist clicks "Wrinkles OK", or straight away when there
   is no wrinkle check).

Everything lives in this one folder. It does NOT need the `ssd_tools` addon or any other file.
Only Blender (4.5.x tested) and Maya (PySide2 or PySide6) must be installed.

## Files

| File | Runs in | Job |
|---|---|---|
| `blend_to_abc_api.py` | Maya | **Entry point for other tools** - one function, no config |
| `run_in_maya.py` | Maya | Stand-alone launcher with a config block (for artists) |
| `maya_side.py` | Maya | Finds/starts Blender, live log + progress bar, ABC naming and safety checks, Maya import |
| `maya_playblast_viewer.py` | Maya | Temporary wrinkle window (play once, smooth fade, OK / Not OK buttons) |
| `blender_run.py` | Blender | Entry script inside headless Blender (finalise -> export -> playblast) |
| `blender_finalise.py` | Blender | Finalise File logic (copied from the ssd_tools addon, no dependency) |
| `blender_export.py` | Blender | Clean & Export ABC logic |
| `blender_playblast.py` | Blender | Wrinkle channel renders (Cycles GPU/CPU, low quality, fast) |

Keep the files together. Each file finds its neighbours from its own location, so the folder can
be moved anywhere (put it on `sys.path`).

## Use from another tool

```python
import sys
sys.path.insert(0, r"C:/path/to/this/folder")
import blend_to_abc_api

abc_path, nodes = blend_to_abc_api.blend_to_abc(
    blend_path=r"P:\...\model_v01.blend",
    output_dir=r"D:\abc_out",
    blender_exe=r"C:/blender/blender-4.5.3-windows-x64/blender.exe",   # "" = auto-detect
)
```

Options (all optional): `abc_name`, `wrinkle_playblast` (default True), `import_into_maya`
(default True), `finalise_options` (dict of the 7 checkboxes), `playblast_options`
(`ramp_steps`, `samples`, `resolution`), `version_from_folder`, `forbidden_roots`, `timeout`.

* `wrinkle_playblast=False` -> fastest: only Finalise + export (+ import).
* `import_into_maya=False` -> only export, returns the `.abc` path (Maya not needed for this).
* Models with no wrinkle shader skip the playblast automatically.
* With the playblast window, `nodes` is `[]` because the import happens when the artist clicks
  "Wrinkles OK - Import ABC into Maya". Closing with "NOT OK" imports nothing (the ABC file stays
  in `output_dir`).

## ABC naming

`<blend file name incl. its own version>_v<NNN>.abc`, where NNN = highest `_vNN` found in the
`.abc` names of `output_dir`, plus 1.
Example: folder has `..._v16.abc` -> `KL_rukmavanarmour_a_workfileMaster_model_v01_v017.abc`.
Existing files are never overwritten.

## Safety rules (built in)

* The source `.blend` is opened and **never saved**.
* `output_dir` is required. The tool **refuses** to write next to the source `.blend` or under
  any `forbidden_roots` (the stand-alone launcher sets `P:/kl_assets`; pass the same from your tool).
* Nothing is ever deleted or overwritten. Only the temporary playblast frames (in the system temp
  folder) are removed when the window closes.

## How it talks to Blender

`maya_side.export_blend_to_abc` starts:

```
blender -b --factory-startup --python-exit-code 1 <file.blend> --python blender_run.py -- ^
    --out <abc> --options <json> [--playblast-dir <tmp> --pb-options <json>]
```

Blender prints progress lines (`[finalise]`, `[export]`, `[playblast] (i/N)`) that Maya shows live
in the Script Editor and in a progress window (ESC cancels). The last line `SSD_RESULT:{json}`
holds the status. Exit code 0 = ABC written.

## Notes and limits

* Wrinkle check expects Character Creator rigs: wrinkle shader (`rl_wrinkle_shader` group) on a
  `*_cc_*_body*` mesh and `*_eye_*` meshes to frame the face. EEVEE is not used (it hit the
  32-sampler limit on the skin shader), Cycles is.
* Measured on the test character: ~110 s total at 512 px / 16 samples; the default is now
  384 px / 8 samples (faster).
* Runs in Maya's main thread but keeps the UI responsive (`processEvents`). Don't start a second
  run while one is active.
* Tested: Blender side end-to-end on Windows, Blender 4.5.3. The Maya window itself was only
  tested offscreen.
