# KRT_02 — Project Progress & Handoff Doc

> **Purpose:** single living document for this project. Any new chat should start by reading this file
> (`C:\pipeline\KRT_02\PROGRESS.md`), then the "Work Log" at the bottom to see where we stopped.
> Update it at the end of every work session. Keep older handoff docs in `Claude outputs/` for history only —
> they are STALE (they describe `C:\Pipeline\KRT` on device "kl201" at Stage 27; the code here is at Stage 40+).

---

## 1. What this project is

**KRT (Kleem Rigging Tool)** — a PySide2/PySide6 Maya tool for procedural biped/creature rig building on top of
mGear's Shifter component system. Two main surfaces:

| Surface | Files | What it does |
|---|---|---|
| **Rig Build Workspace** | `workspace.py`, `widgets.py` | Linear panel-stack per LOD (Script, Import 3D, Skin, Control Shapes, Publish, Module Bubbles, Tweaker, LOD Loader, Playblast…). Runs top-to-bottom, with per-step scene caching. |
| **Module Graph Editor** | `graph.py` | Node graph; each node = an mGear Shifter component guide (or Plebe biped template / Custom `.sgt` / Custom Script node). Wires define parent/child guide relationships. Builds real guides + rigs via Shifter API. Has its own undo/redo. |

Also includes: AYON publish dialog (`dialogs.py`), Tweaker (facial micro-controls) module (`PanelScripts/Tweaker.py`),
Playblast tab with ffmpeg encode + wipe-compare player, fast skin export/import via OpenMaya API (`utils.py`).

## 2. Key facts

- **Location:** `C:\pipeline\KRT_02` on device **kla04**. Python package name is **`KRT`** (all imports are `KRT.xxx`) — the
  installer (`DRAG_DROP_TO_MAYA.py`) copies the folder into Maya's scripts dir as `KRT`. Running straight from `KRT_02` requires
  the folder be importable under the name `KRT` (e.g. rename/junction) — confirm how it is actually launched today.
- **Launch:** `KRT` shelf button / `KRT` menu → `KRT.menu.launch()` → reloads `KRT.*` modules → `KRT.main.run_tool()`.
  `run.py` is an alternate "hard reload" launcher.
- **Qt:** `compat.py` picks PySide6 (Maya 2025+) or PySide2. Multimedia + wipe-compare degrade gracefully if Qt lacks them.
- **Dependencies:** Maya (`maya.cmds`, OpenMaya 1.0 + 2.0 API), mGear (Shifter, io, plebe), `ayon_api` (publish), ffmpeg (playblast encode).
- **Original author header:** `main.py` docstring names Vishal Nagpal as owner/POC.
- **No git repo yet.** Strongly recommended: `git init` in `KRT_02` so every session's change is diffable/revertable.
- **Cannot run Maya from Claude.** Verification = `py_compile` + AST duplicate-method scan + reading mGear source. Every change
  must be tested by the user in a real Maya session. Maya caches modules — **relaunch via the KRT menu (it reloads) or restart Maya**
  before reporting a fix "didn't work".

## 3. Codebase map (as of 2026-09-18, ~20,100 lines)

| File | Lines | Contents |
|---|---|---|
| `main.py` | 345 | `KRT_Tool` (MayaQWidgetBaseMixin QDialog): tabs of sessions, autosave timer (5 min), crash-health check on startup, styling. `run_tool()`. |
| `workspace.py` | 5037 | `SessionWorkspace` (**159 methods, one class**) — pages: File, Rig (LOD panel stacks), Docs, Profile/notes, Scripts library, Playblast. Full build / build-till-here / cache-resume logic, panel serialize/restore + undo of panel delete, pipeline JSON save/load/versions, all panel-type executors (`run_script`, `import_3d_logic`, `load_skin_cluster_logic`, `run_tweaker_logic`, `publish_asset_logic`…), playblast pipeline (`pb_*`, ~60 methods), LOD sequence build. `CurrentPageStackedWidget`. |
| `widgets.py` | 4706 | `SortablePanel` (45 methods — generic step row: script/MA/skin/shapes/publish/tweaker), `SortableBubblePanel` (LOAD MODULE panel w/ `ModuleBubble`s, batch guide build/delete), `LodLoaderPanel`, `CacheMixin` (per-step `.ma` cache buttons), `FlowLayout`, drag/drop containers, `GraphNodeOrderDialog`, `TweakerVertexGroup`, `PBCameraViewWidget` (embedded model panel), `PBWipeCompareWidget` (PySide6 only). |
| `graph.py` | 5378 | `RigNode`, `RigWire`, `NodeGraphView` (mouse/keys, wire drag, context menu, copy/cut/paste/duplicate), `NodeSearchPopup`, `GuideSettingsPanel` (mirrors mGear guide root settings: rig/anim/skin/joint/color/custom steps/naming/blueprint), `ModuleGraphWidget` (85 methods — business logic: build guides, Plebe ops, custom sgt/script nodes, attach-under resolution `_resolve_attach_parent`, guide position capture/apply, main-settings live apply, save/load guides, snapshot undo/redo, `execute_graph_nodes`). Defaults: `DEFAULT_CONTROL_SHAPES_LIBRARY`, fan/stretchy joint scripts. |
| `dialogs.py` | 1912 | `AdvancedSaveDialog`, `SaveCommentDialog`, `BuildProgressDialog`, `PathReplaceDialog`, `CreateFolderStructureDialog`, `AyonPublishDialog` (21 methods: publishes rig + work folder to AYON via `ayon_api`/EntityHub), `SimpleCodeEditorDialog`, JSON path helpers. |
| `utils.py` | 1632 | Versioned paths, control-shape export/import + library apply, material export/import (shader network capture), skinCluster naming/mismatch/re-skin helpers, crash log + session health markers, **fast skin export/import (OpenMaya API)**. |
| `session.py` | 109 | `SessionManager` — session json (notes, recents, autosaves, published). |
| `compat.py` | 54 | Qt binding shim (see above). |
| `menu.py`, `run.py` | 39/16 | Launchers. |
| `DRAG_DROP_TO_MAYA.py` | 285 | Drag-into-Maya installer: copies package, makes shelf + menu, installs `userSetup.py` auto-menu hook. |
| `PanelScripts/Tweaker.py` | 595 | Standalone Tweaker system: per-vertex follicle+plane control, skin copy, auto-weight falloff, blendshape hookup. |

**Data files:** pipeline JSON (per LOD panel stack, with step uuids), graph config JSON (nodes/wires/fields), step caches
`<MayaAppDir>/KleemRiggingTool/step_caches/<uuid>.ma`, sessions under `<MayaAppDir>/KRT/Sessions`, autopublish under `<MayaAppDir>/KRT/AutoPublish`.

## 4. Feature history (condensed)

Stages are the user's numbered requests; code comments say `Stage N` where a change lives (`grep -n "Stage 3" *.py`).

- **≤10** window sizing, per-bubble & panel LOAD buttons (batch build / delete guides).
- **11–13** Control Shapes Library (Plebe-only), drag-reorder bubbles, Save Guides → `guide/` subfolder, "Build Parent's Guide" button,
  Custom `.sgt` module node, multi-select-in-order dialog for adding graph modules to a panel.
- **14** Graph undo/redo (snapshot stack, 60 deep, Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y); `_resolve_attach_parent` self-healing stale attach locators.
- **16** crash log + "last session ended badly" startup check. **17** Playblast tab w/ embedded QMediaPlayer.
- **24** build on top of existing scene (no wipe). **25** module-reload false-bug lesson.
- **26** searchable Attach Under combo; Custom Script Module (guide-less) node.
- **27** mGear per-component Main Settings in Node tab (live apply); node Copy/Cut/Paste/Duplicate.
- **28–31** (see `grep "Stage 28"` etc.) heavy work in graph/widgets — guide position capture/apply & position watch, component settings capture, joint names editing, RGB color picker, UI-host grab.
- **33–36** AYON publish dialog rules (Stage 35 rule 2: publish also writes pipeline JSON), folder-structure creation dialog, path replace.
- **37–40** Playblast: camera generation/AOV, metadata burn-in via ffmpeg, HUD/gate hiding, StudioLibrary anim load on filtered controls, compare mode, **wipe/slider compare (PySide6 QVideoSink)**.
- **Caching & speed pass** (`BUILD_SPEED_NOTES.md`): per-step cache/load/build-from-cache, fast-build context (undo off, echo off, refresh suspended), per-step timings.

## 5. Review findings (2026-09-18 full-code scan)

Health: all files compile (`py_compile` clean); **no duplicate method definitions** in any class; no TODO/FIXME markers left.

Observations / candidates for future work (not yet done — decide together):

1. **Hardcoded personal dev paths** in `workspace.py::setup_default_panels` (lines ~770–776, `E:\Pipe_Storage\Vishal_workspace\...`) — defaults for a
   new LOD point at another artist's disk. Should become blank or a configurable studio default.
2. **Hardcoded network defaults**: `P:\pipeline_database\Maya\Scripts\ONE` (workspace.py:27, session.py:35), `P:\rigging_team\...studiolibrary`,
   `R:\Pipeline_Share\...\controlShapes.ma` (graph.py:53), ffmpeg/font search paths (workspace.py:3450–3464). Fine for now; consider a `config.json`.
3. **`SessionWorkspace` is 5k lines / 159 methods.** The `pb_*` playblast block (~60 methods) is the obvious extraction into its own module
   (`playblast.py`) if we ever refactor. Same for build-execution logic.
4. **User-facing "AYON" text** in `dialogs.py` (window title "Publish Rig to AYON — KRT", "AYON Context" group, "AYON API is not connected", `[AYON PUBLISH]` prints).
   Per your standing rule, UI text should say **KRISHNA** (internals like `ayon_api`, env vars, `ayon:5000` untouched). **Pending your go-ahead.**
5. **Naming:** your tools carry an `ssd_` prefix; this one is `KRT` (package name baked into installer, menu, shelf, userSetup hook, `run.py`).
   Renaming is doable but touches launch/install — **decide whether KRT stays as-is.**
6. **Stale docs:** `Claude outputs/HANDOFF.md` and `KRT_AI_HANDOFF.md` reference the old location/device and a claude.ai project doc that no longer applies.
   This `PROGRESS.md` supersedes them.
7. **No version control.** `git init` + first commit recommended before further edits.
8. Old known-unverified item from Stage 14: Custom `.sgt` node built with **no** Attach Under locator relies on PyMEL `getParent(-1)` behaviour on a
   parentless node — never confirmed. Workaround: always pick a locator.

## 6. How we verify a change (you can run these yourself)

Open a terminal in `C:\pipeline\KRT_02` and run:

```bat
:: 1) Syntax check — catches typos/indent errors instantly, no Maya needed
python -m py_compile graph.py widgets.py workspace.py dialogs.py utils.py main.py

:: 2) Duplicate-method scan — a second `def foo` in the same class silently replaces the first
python -c "import ast,sys
for f in ['graph.py','widgets.py','workspace.py','dialogs.py','utils.py','main.py']:
    for c in ast.walk(ast.parse(open(f,encoding='utf-8').read())):
        if isinstance(c,ast.ClassDef):
            s={}
            for m in c.body:
                if isinstance(m,ast.FunctionDef):
                    if m.name in s: print('DUP',f,c.name,m.name,s[m.name],m.lineno)
                    s[m.name]=m.lineno
print('scan done')"
```

Then in Maya: **KRT menu → launch** (reloads modules) and test the actual behaviour. Report back what happened.

## 7. Working agreement

- One "Stage" = one numbered request set → code → verify → test in Maya → log it here.
- Quote the request verbatim in the Work Log; flag anything inferred rather than confirmed from mGear source.
- Edit files in place on kla04 (`C:\pipeline\KRT_02`), never re-type file contents from memory.
- Read the relevant section of mGear source (`...\maya\modules\scripts\mgear`) when Shifter behaviour matters — don't guess.

---

## 8. Work Log (newest first)

### 2026-09-18 — Session 1: full code review + this document
- Read all 15 source files (AST outline of every class/method), both old handoff docs and `BUILD_SPEED_NOTES.md`.
- Verified: everything compiles, no duplicate methods, no TODO markers. Latest stage marker in code: **Stage 40**.
- Created `PROGRESS.md` (this file). No code changed.
- **Open decisions for user:** items 1, 4, 5, 7 in §5.
- **Next:** user picks first Stage of work for KRT_02.
