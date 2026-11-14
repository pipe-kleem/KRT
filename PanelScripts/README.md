# PanelScripts

The scripts that power KRT's special panels. Edit them here - KRT picks them up the next time it is installed/reloaded.
(The generic panels - Script, Model, JSON skin, Shapes, Materials - use the core code in `utils/`, not this folder.)

| Panel | Script(s) here |
|---|---|
| TWEAKER | `Tweaker.py` (loaded by file path) |
| FACIAL SHAPE EXTRACT | `facial_shape_extract.py` (source mesh -> wrap -> blendShape on each target) |
| BREATHING | `breathing.py` |
| CC IMPORT | `cc_import.py`, `cc_autosetup.py` (drives Reallusion Auto Setup) |
| JOINT TRANSFER | `joint_transfer.py` (+ helpers `rig_resources.py`, `rig_reference.py`, `step_runner.py`) |
| FINGER FIX | `finger_fix.py` (+ the same helpers) |
| JOINT POSITIONS | `joint_positions.py` |
| IMPORT 3D + LOD ORGANIZE (BLENDER) | `blend_abc_tool/` (headless Blender export, wrinkle check, mesh compare) |

Rules of thumb:
- A new panel's script goes here and is imported in `widgets/sortable_panel.py` with `from ..PanelScripts import <name>`.
- The `rig_resources` / `rig_reference` / `step_runner` helpers are shared by Joint Transfer and Finger Fix - change them with care.
- Keep `from ..compat import ...` style relative imports; this folder sits next to `utils/`, `widgets/`, `workspace/`.
