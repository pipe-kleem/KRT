# KRT_02 — Project Progress & Handoff Doc

> **Purpose:** single living document for this project. Any new chat should start by reading this file
> (`C:\pipeline\KRT_02\PROGRESS.md`), then the "Work Log" at the bottom to see where we stopped.
> Update it at the end of every work session. Old handoff docs are in `archive/claude_outputs_old_handoffs/` for history only —
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

## 3. Codebase map (as of 2026-09-18, after restructure — ~20,300 lines, 45 files)

Package name is still `KRT`; **every public import path is unchanged** (`from .widgets import SortablePanel`, `from .graph import ModuleGraphWidget` …)
because each package's `__init__.py` re-exports everything. Inside a package, `_shared.py` holds the original module's imports + constants + small helpers,
and every sibling file starts with `from ._shared import *`.

Giant classes were split into **mixins**: the class keeps `__init__`, class attributes and core methods in one file; groups of related methods live in
`*_<group>.py` as `class <Name><Group>Mixin(object)`. The real class inherits all its mixins, so `self.anything` works exactly as before.
Rule of thumb: **to find a method, grep for `def name`** — it lives in exactly one file.

| Path | Lines | Contents |
|---|---|---|
| `main.py` | 345 | `KRT_Tool` window, tabs, autosave timer, crash-health check, `run_tool()`. |
| `compat.py` / `session.py` / `menu.py` / `run.py` | 54/109/39/16 | Qt shim; `SessionManager`; launchers. |
| `DRAG_DROP_TO_MAYA.py` | 285 | Drag-into-Maya installer (shelf + menu + userSetup hook). |
| `PanelScripts/Tweaker.py` | 595 | Standalone Tweaker algorithm (loaded by path from `workspace/executors.py`). |
| **`utils/`** | | |
| `utils/paths.py` | 32 | `get_versioned_path` |
| `utils/control_shapes.py` | 271 | control-shape export/import, `find_guide_model`, `apply_control_shapes_library` |
| `utils/materials.py` | 442 | material/shader-network export + import |
| `utils/skin.py` | 330 | skinCluster naming/mismatch/re-skin helpers, skin-file readers |
| `utils/crash_log.py` | 129 | crash log + session start/clean-exit markers |
| `utils/fast_skin.py` | 345 | OpenMaya-API fast skin export/import |
| **`dialogs/`** | | |
| `dialogs/save_dialogs.py` | 346 | `AdvancedSaveDialog`, `SaveCommentDialog`, `BuildProgressDialog`, `SimpleCodeEditorDialog` |
| `dialogs/path_tools.py` | 549 | `PathReplaceDialog`, `CreateFolderStructureDialog`, JSON path helpers |
| `dialogs/ayon_publish.py` | 1011 | `AyonPublishDialog` (the only place `ayon_api` is imported) |
| **`widgets/`** | | |
| `widgets/style.py` | 105 | panel colour/icon helpers, `panel_run_label`, `prompt_skincluster_naming_check` |
| `widgets/dialogs.py` | 157 | `ErrorDialog`, `GraphNodeOrderDialog` |
| `widgets/flow_layout.py`, `drag_drop.py`, `cache_mixin.py`, `tweaker_group.py` | 142/36/146/201 | `FlowLayout`; `DragDropContainer`; `CacheMixin` (per-step cache buttons); `TweakerVertexGroup` |
| `widgets/sortable_panel.py` | 1662 | `SortablePanel` — generic step row (script/MA/skin/shapes/publish/tweaker) |
| `widgets/bubble_panel.py` | 1135 | `ModuleBubble`, `BubbleDropArea`, `SortableBubblePanel` (LOAD MODULE panel) |
| `widgets/lod_loader.py` | 532 | `LodLoaderBubble`, `LodLoaderPanel` |
| `widgets/playblast_widgets.py` | 499 | `PBCameraViewWidget`, `PBWipeCompareWidget` |
| **`graph/`** | | |
| `graph/_shared.py` | 88 | node-type constants, default control-shapes lib path, default fan/stretchy joint scripts |
| `graph/catalog.py` | 97 | `list_mgear_components` (+cache), `list_plebe_templates`, `_find_guide_root` |
| `graph/items.py` | 443 | `RigWire`, `RigNode`, `bezier_path` |
| `graph/dialogs.py` | 358 | `CustomScriptDialog`, `AutoScriptEditDialog`, `PlebeTemplateDialog`, `NodeSearchPopup` |
| `graph/view.py` | 648 | `NodeGraphView` — mouse/keys, wire drag, context menu, copy/cut/paste/duplicate, node creation |
| `graph/guide_settings.py` | 518 | `CustomStepListEditor`, `GuideSettingsPanel` (mGear guide-root settings tab) |
| `graph/widget.py` | 1010 | `ModuleGraphWidget` core: `__init__`, side panel/Node tab UI, `update_attr_editor`, `on_attr_changed`, parent combo |
| `graph/widget_positions.py` | 366 | `GraphPositionsMixin` — guide position capture/apply, position watch |
| `graph/widget_component_settings.py` | 600 | `GraphComponentSettingsMixin` — mGear Main Settings, attach-under combo, joint names, colour, `apply_main_settings_live` |
| `graph/widget_scripts.py` | 216 | `GraphScriptsMixin` — custom/fan/stretchy scripts, control-shapes library browse/apply |
| `graph/widget_io.py` | 353 | `GraphIoMixin` — guide path defaults, save/load guides, `serialize_node`/`deserialize_node`, graph config data |
| `graph/widget_undo.py` | 117 | `GraphUndoMixin` — snapshot undo/redo |
| `graph/widget_build.py` | 635 | `GraphBuildMixin` — Plebe ops, `_resolve_attach_parent`, all `_build_*` methods, `build_node_guide`, `execute_graph_nodes` |
| **`workspace/`** | | |
| `workspace/core.py` | 315 | `CurrentPageStackedWidget`; `SessionWorkspace` core: `__init__`, `setup_ui`, nav, session lists, autosave toggle |
| `workspace/lods.py` | 278 | `WorkspaceLodsMixin` — LOD list, create/delete LOD, default panels, LOD loader panel, LOD sequence build |
| `workspace/pages.py` | 694 | `WorkspacePagesMixin` — File / Rig / Docs / Profile / Scripts-library pages, module list ↔ graph sync |
| `workspace/panels.py` | 242 | `WorkspacePanelsMixin` — add/duplicate/delete panel, serialize/restore, panel-delete undo |
| `workspace/build.py` | 433 | `WorkspaceBuildMixin` — full build, build-till-here, cache clear/resume, fast-build context, timings |
| `workspace/pipeline_io.py` | 466 | `WorkspacePipelineIoMixin` — pipeline JSON data/save/load/versions, autosave, publish paths |
| `workspace/executors.py` | 783 | `WorkspaceExecutorsMixin` — every panel-type action: scripts, import 3D, instances, skin, re-skin, tweaker |
| `workspace/playblast.py` | 1844 | `WorkspacePlayblastMixin` — all `pb_*`, camera generation, ffmpeg encode, compare mode, Playblast page |
| **`tools/`** | | `smoke_test.py` (import test outside Maya), `smoke_stubs/` (fake maya/PySide2/ayon_api), `restructure/split_krt.py` (the one-off splitter, for reference) |

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
- **Caching & speed pass** (`archive/BUILD_SPEED_NOTES.md`): per-step cache/load/build-from-cache, fast-build context (undo off, echo off, refresh suspended), per-step timings.

## 5. Review findings (2026-09-18 full-code scan)

Health: all files compile (`py_compile` clean); **no duplicate method definitions** in any class; no TODO/FIXME markers left.

Observations / candidates for future work (not yet done — decide together):

1. **Hardcoded personal dev paths** in `workspace.py::setup_default_panels` (lines ~770–776, `E:\Pipe_Storage\Vishal_workspace\...`) — defaults for a
   new LOD point at another artist's disk. Should become blank or a configurable studio default.
2. **Hardcoded network defaults**: `P:\pipeline_database\Maya\Scripts\ONE` (workspace.py:27, session.py:35), `P:\rigging_team\...studiolibrary`,
   `R:\Pipeline_Share\...\controlShapes.ma` (graph.py:53), ffmpeg/font search paths (workspace.py:3450–3464). Fine for now; consider a `config.json`.
3. ~~`SessionWorkspace` is 5k lines / 159 methods~~ — **done 2026-09-18** (split into 8 files via mixins, see §3). Biggest remaining files: `workspace/playblast.py` (1844), `widgets/sortable_panel.py` (1662).
4. **User-facing "AYON" text** in `dialogs.py` (window title "Publish Rig to AYON — KRT", "AYON Context" group, "AYON API is not connected", `[AYON PUBLISH]` prints).
   Per your standing rule, UI text should say **KRISHNA** (internals like `ayon_api`, env vars, `ayon:5000` untouched). **Pending your go-ahead.**
5. **Naming:** your tools carry an `ssd_` prefix; this one is `KRT` (package name baked into installer, menu, shelf, userSetup hook, `run.py`).
   Renaming is doable but touches launch/install — **decide whether KRT stays as-is.**
6. **Stale docs:** `archive/claude_outputs_old_handoffs/*.md` reference the old location/device and a claude.ai project doc that no longer applies.
   This `PROGRESS.md` supersedes them.
7. ~~No version control~~ — **git repo initialised 2026-09-18**; baseline commit before restructure, one commit per stage from now on.
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

:: 3) Undefined-name check + import smoke test (run this after ANY edit)
::    - undefined-name check: names a module uses but never binds (NameError waiting to happen)
::    - import test: loads the whole package with fake Maya/Qt stubs
python tools\smoke_test.py
```

Then in Maya: **KRT menu → launch** (reloads modules) and test the actual behaviour. Report back what happened.

## 7. Working agreement

- One "Stage" = one numbered request set → code → verify → test in Maya → log it here.
- Quote the request verbatim in the Work Log; flag anything inferred rather than confirmed from mGear source.
- Edit files in place on kla04 (`C:\pipeline\KRT_02`), never re-type file contents from memory.
- Read the relevant section of mGear source (`...\maya\modules\scripts\mgear`) when Shifter behaviour matters — don't guess.

---

## 8. Work Log (newest first)

### 2026-09-18 — Session 2: restructure into packages + mixins  (commit `0301516`)
- Request: *"lets restructure all the code first divide in multiple files so its faster to edit and work in it"*. Chosen style: folders + mixins.
- `git init` done; baseline commit `8b8c487` (user had already made `da8fb00`). Added `.gitignore` (`__pycache__`, `*.pyc`).
- Wrote an AST/line-range splitter (`tools/restructure/split_krt.py`) so comments and formatting survived; no code was re-typed by hand.
- `utils.py`, `dialogs.py`, `widgets.py`, `graph.py`, `workspace.py` → packages (see §3). `ModuleGraphWidget` → core + 6 mixins; `SessionWorkspace` → core + 7 mixins.
- Mechanical edits inside mixins: `super(ClassName, self)` → `super()`; `SessionWorkspace._pb_settings_clipboard` → `type(self)._pb_settings_clipboard`.
- One real path fix: `workspace/executors.py::_load_tweaker_module` now goes up two dirs to find `PanelScripts/Tweaker.py`.
- Verification: every class/method/function accounted for exactly once (AST inventory diff); all files compile; `tools/smoke_test.py` imports the whole
  package with stubs — no circular imports, MROs resolve. **Not yet launched in Maya** — that is the first thing to do next session
  (KRT menu → launch; if it errors, paste the traceback).
- Known cosmetic side-effect: `_shared.py` re-exports all of a module's original imports, so sibling files see unused names like `cmds`/`os` even when they don't need them. Harmless.

### 2026-09-18 — Session 1: full code review + this document
- Read all 15 source files (AST outline of every class/method), both old handoff docs and `BUILD_SPEED_NOTES.md`.
- Verified: everything compiles, no duplicate methods, no TODO markers. Latest stage marker in code: **Stage 40**.
- Created `PROGRESS.md` (this file). No code changed.
- **Open decisions for user:** items 1, 4, 5, 7 in §5.
- **Next:** user picks first Stage of work for KRT_02.

### 2026-09-18 — Session 2b: installer check + archive folder
- `DRAG_DROP_TO_MAYA.py` already copies sub-folders recursively, so the new packages install fine. Added: skips `tools/`, `archive/`, `*.md`;
  new `_remove_stale_modules()` deletes leftover single-file `graph.py`/`widgets.py`/… from an older install so they can't shadow the packages.
- Created `archive/`: old Claude handoff docs, `BUILD_SPEED_NOTES.md` (still useful — optimisation ideas list), the one-off splitter script.

### 2026-09-18 — Session 3 / Stage 41: Rig Root relative paths + Qt page-switch sizing
Request (verbatim): *"I want to make this relative … in the ui 1 path and everything under that path … root path - P:/rigging_team/Rigging_local_share/all_Rigs/blindfold_a/ and each portion should have only this - scripts/utils.py … second important update is there is some ui scaling issue when going to graph and coming back it stucks, overall check qt issues"*

**Relative paths**
- New `utils/relpath.py` — pure-string `resolve(root, p)` / `relativize(root, p)`; non-path text (inline code, `GRAPH::uuid`) passes through untouched. Unit-tested offline.
- New mixin `workspace/root_path.py` (`WorkspaceRootPathMixin`): `rig_root()`, `resolve_path()`, `relativize_path()`, `set_rig_root()`, `relativize_all_paths()`, `infer_rig_root_from_panels()`.
- UI: **Rig Root** row under the Rig Name header (`pages.py`) — field + 📁 browse + "⇄ Make Relative". Editing the root re-shortens every path under it live.
- JSON: new top-level `"root_path"`. Panel `path`, module bubble `path`, graph `custom_sgt_path` / `plebe_template_path` / `control_shapes_library` saved relative when under root. Loading a **legacy JSON with no `root_path`** adopts the active PUBLISH folder as root and shortens on screen (nothing written until saved).
- Every disk read now goes through resolve: `SortablePanel.path()` (new; replaced 22 `self.field.text()` reads), bubble `.py`/`.sgt` runs, graph builds, guide path field, publish-dir lookups (`pipeline_io`, `build.py`, `ayon_publish`). Browse/save dialogs write back relative.
- Inline scripts get a `RIG_ROOT` variable in the shared namespace.
- Not rewritten on purpose: absolute paths **inside** inline script code (e.g. the `Load_Guide` panel) — use `RIG_ROOT` there by hand.

**Qt sizing** (`workspace/core.py::CurrentPageStackedWidget`)
- Root cause hypothesis: `minimumSizeHint()` forwarded the current page's minimum, so returning from Graph (compact) to Rig (wide header ≈1100px) raised the window minimum mid-flight → jump, or a half-laid-out page when the window couldn't grow. Now a small fixed floor (360×240) + a deferred relayout (`QTimer.singleShot(0)`) after every page switch.
- **Unverified in Maya.** If it still sticks, need: screenshot + whether window is floating/docked + which page → page.
- Perf note (not changed): the graph's position-watch timer reads t/r/s of every guide transform every 1.5 s while the Graph page is visible — can feel laggy with big guides. Candidate follow-up.
- **Installer fix (same session):** user reported drag-drop "didn't update". `DRAG_DROP_TO_MAYA.py` now: closes a running KRT window, **wipes the old install folder** before copying, forces the scripts dir to the FRONT of `sys.path`, and after import prints which folder `KRT` actually loaded from — warns loudly if another KRT copy on `sys.path` shadowed the fresh install (the most likely cause of "didn't update").
- **Version stamp (2026-09-19):** `__init__.py` now carries `__version__` (currently **41.2**), shown in the KRT window title (`KRT 41.2 | Procedural Builder`) and printed by the installer both for the SOURCE folder it copies from and for the package Maya actually imports. Added because a drag-drop from `//kla04/pipeline/KRT_02` installed 32 files — no commit of `C:\pipeline\KRT_02` ever had 32 files, so that share mirrors a DIFFERENT, older copy. Always drag from the local path `C:\pipeline\KRT_02\DRAG_DROP_TO_MAYA.py`.

### 2026-09-19 — Stage 41 hotfix (v41.3)
- **`SortablePanel.path()` recursed infinitely** → "maximum recursion depth exceeded" on launch. Cause: the bulk edit that routed 22 `self.field.text()` reads through the new `path()` helper also rewrote the helper's own body. Fixed + added an AST self-call scan to the checks. Lesson: after a bulk rename, exclude the newly-added definition.
- **Playblast live-viewport MEL errors** (`createModelPanelBar |||KRT_pbCamView…` / `Line 1.22: Syntax error`): the Qt widgets wrapping the embedded Maya modelPanel had no `objectName`, so Maya built a UI path with empty segments (`|||`). Named the widget chain (`…Outer`, `…Widget`) to match Studio Library's ModelPanelWidget. **Hypothesis — needs confirming in Maya.**

### 2026-09-19 — Stage 41 hotfix 2 (v41.4): graph mixins were missing sibling imports
- Symptom: loading any pipeline JSON with graph nodes → `NameError: name 'RigNode' is not defined` in `graph/widget_io.py::deserialize_node`.
- Cause: the restructure splitter computed cross-file imports for every file but **never wrote them into the mixin files**. All six `graph/widget_*.py` mixins were affected (`RigNode`, `RigWire`, `_find_guide_root`, `list_plebe_templates`, `PlebeTemplateDialog`, `CustomScriptDialog`, `AutoScriptEditDialog`). `workspace/` mixins were unaffected — they get those names from `_shared.py`.
- Why the earlier checks missed it: `py_compile` and the import smoke test only execute a module's **top level**. A missing name inside a method body is invisible until that method runs in Maya.
- New guard: **`tools/check_names.py`** — static free-name analysis per module, reporting anything used but never bound, plus which sibling module defines it. Now runs automatically at the start of `tools/smoke_test.py`. Target output: `files with holes: 0`. (Limitation: it treats a name bound anywhere in a module as bound everywhere, so it under-reports rather than false-alarms.)
- Also seen in the log and harmless: `Warning: Invalid Path provided.` is `main.py::load_path_from_field` — the Load button beside Current Path with an empty/invalid path.

### 2026-09-19 — Stage 41 hotfix 3 (v41.5): 17 broken relative imports inside function bodies
- Symptom: `No module named 'KRT.workspace.utils'` when loading a skinCluster (and the same waiting to happen in 16 other places).
- Cause: the restructure moved files one level deeper, so a `from .utils import …` written **inside a method body** now resolves to `KRT.<package>.utils` instead of `KRT.utils`. The splitter rewrote only the module-level imports it moved into `_shared.py`. Function-level imports don't run at import time, so nothing caught them until the button was clicked.
- Fixed all 17 (`.utils`→`..utils`, `.graph`→`..graph`, `.widgets`, `.dialogs`, `.compat`) in `graph/widget_io.py`, `graph/widget_scripts.py`, `widgets/bubble_panel.py`, `widgets/playblast_widgets.py`, `widgets/sortable_panel.py`, `workspace/executors.py`, `workspace/pages.py`, `workspace/pipeline_io.py`.
- `tools/check_names.py` now also **validates every relative import**: that the target module exists at that dot-depth, and that each imported name is actually exported by it. Target output is now two zeros — `files with holes: 0` and `broken relative imports: 0`.

### 2026-09-19 — v41.6: playblast modelPanel orphans (`updateModelPanelBar ... Syntax error`)
- Symptom: repeated `updateModelPanelBar ||||||||KRT_pbCamViewNNN...` / `Line 1.22: Syntax error`, with **several different NNN ids** and a growing number of leading `|`.
- Root cause: `cmds.modelPanel` creates a **Maya UI object, not a Qt child**. `PBCameraViewWidget.stop()` only stopped its poll timer, so every KRT relaunch / closed session tab left a live orphan panel in Maya. Maya keeps refreshing each one forever; the empty `|` segments are its vanished Qt ancestors, and the count grew with each orphan. (The v41.3 objectName change was treating a symptom — the real issue was orphan accumulation.)
- Fix: `stop()` now calls `cmds.deleteUI(panel, panel=True)`; new `PBCameraViewWidget.cleanup_stale_panels()` sweeps every `KRT_pbCamView*` panel and is called from `run_tool()` on launch (reports how many it removed) and from `KRT_Tool.closeEvent`; `close_session()` stops a closed tab's viewport first.
- **First launch after this update still has the old orphans from the running Maya session** — they are swept on launch and reported, but a Maya restart is the clean baseline for confirming the spam is gone.

### 2026-09-19 — v41.8: "Build Till Here" silently resumed from cache instead of building
- Symptom, from the user's log: `--- Starting Partial Procedural Build ---` → `Resuming from cache 'CONTROL SHAPES' (step 7)` → `Partial Build Finished` in **00:00**, having run only the two steps after the cache. Model/skin/guide steps never re-ran, so the scene didn't match the panels. Reported as "Build Till Here is not working" — it ran, it just didn't build.
- Cause: `build_till_panel()` always searched backwards for the newest cached step before the target and jumped there. Unconditional, and only mentioned in one warning line. `BUILD_SPEED_NOTES.md` documents the opposite ("Build Till Here does the same [as a full build] but only up to the target step").
- Fix: `build_till_panel(target_panel, resume_from_cache=False)`. The context menu now has **two** entries in all three panel types:
  - `🚀 Build Till Here (run every step)` — default; wipes the scene and runs steps 1..target.
  - `⚡ Build Till Here (resume from newest cache)` — the old fast behaviour, now explicit; says so when no cache exists before the target.
- Also from the same log: the user was still running a build **older than 41.7** (none of the new `print()` diagnostics appeared, and the same two orphan `KRT_pbCamView` ids persisted) — the v41.6 orphan sweep never ran.

### 2026-09-19 — v41.9: the `createModelPanelBar / updateModelPanelBar ... Syntax error` noise
- After v41.6 swept the orphans (log shows `cleanupModelPanelBar` firing on the old ones), a **single** live panel still errored — so orphan accumulation was only half the story.
- Real cause: Maya builds a UI path by joining the Qt **objectNames** of the whole ancestor chain with `|`. Every *unnamed* widget contributes an empty segment. KRT embeds the viewport ~9 layers deep, giving `KRT_Window||||||||||KRT_pbCamViewNNNLayout|…`, which Maya's own `createModelPanelBar` / `updateModelPanelBar` / `cleanupModelPanelBar` MEL procs can't parse. (v41.3 named only 2 widgets of the chain — that's why the pipe count changed but the error didn't go away.)
- Fix: `_name_ancestor_chain()` walks from the widget up to the top-level window and gives every unnamed widget a unique objectName, stopping at the window so Maya's own UI is never renamed. Run at construction **and** in `showEvent` — the widget is built before it is added to its parent layout, so at `__init__` the chain is still short (that is why the first error showed 3 pipes and later ones 10). Panel creation is also wrapped in `_quiet_script_editor`.
- Safe by construction: setting a previously-empty objectName can only add matches for `#name` stylesheet selectors, and the generated names are unique per widget.

### 2026-09-19 — Stage 42 (v42.0): studio default path + Initialize Project
Request: default path everywhere should be `P:\rigging_team\Rigging_local_share\all_Rigs`; if a base path is set, that wins. Plus an **Initialize Project** button that creates the standard folders, copies `utils.py` into `scripts/`, and builds the panel stack from a rig name.

**Default browse path**
- `utils/paths.py::DEFAULT_RIGS_ROOT = P:\rigging_team\Rigging_local_share\all_Rigs`.
- New `SessionWorkspace.default_browse_dir()` — **Rig Root first, then DEFAULT_RIGS_ROOT**, never an empty string when the folder exists (an empty `dir` makes Maya's file dialog reopen wherever it last was, anywhere on the machine).
- Wired into: panel Browse (`SortablePanel.get_start_dir`), Rig Root browse, module-bubble browse (prefers `guides/` under the root), graph Control-Shapes-Library browse, graph `.sgt` browse, Load Pipeline JSON browse.

**Initialize Project** (`✨ Initialize Project`, next to Rig Root)
- `dialogs/project_init.py::ProjectInitDialog` — rigs folder (defaults to `DEFAULT_RIGS_ROOT`), rig name, live preview of the folders, three opt-outs (copy utils.py / create panels / open in Explorer).
- `workspace/project_init.py::WorkspaceProjectInitMixin.initialize_project()` creates
  `<rigs>/<name>/{cc_rig, controlShape, guides, model, module, playblasts, rig, scripts, skinCluster}`,
  copies the bundled `templates/utils.py` → `scripts/utils.py`, sets the Rig Root, fills the Rig Name as `<name>_rig`, sets the playblast output to `playblasts`, and creates the default panel stack with **relative** paths:
  | panel | type | path |
  |---|---|---|
  | MAYA GLOBAL SCRIPT | GLOBAL_SCRIPT | — |
  | LOAD SCRIPT PANEL | SCRIPT | `scripts/utils.py` |
  | LOAD MODEL (3D file) | IMPORT_3D | `model/export.abc` |
  | LOAD MODULE | MODULE | (bubbles) |
  | LOAD SKINCLUSTER | JSON | `skinCluster/skinCluster.jSkin` |
  | CONTROL SHAPES | SHAPES | `controlShape/controlShapes.json` |
  | PUBLISH PATH | PUBLISH | `rig` |
- **Non-destructive**: an existing folder is left alone, an existing `scripts/utils.py` is never replaced. Only "create default panels" is destructive, and it clears the *current LOD's* panels — it is a checkbox, on by default.
- `templates/utils.py` is the user's own utils (repath_textures, organize_and_convert_lod, wrap/blendshape/joint helpers…), shipped with the package so it installs with KRT.
- Verified offline: folder creation, the 49KB template copy, and a second run creating nothing.
- **Guesses worth correcting if wrong:** `PUBLISH PATH → rig` (the old blindfold JSON used the rig root itself), and `model/export.abc` as the model filename.

### 2026-09-19 — v42.1: Rig Root path button is now a relative/absolute toggle
- `⇄ Make Relative` was one-way. It is now **`⇄ Paths: Relative` / `⇄ Paths: Absolute`** — the label names the state the paths are in *now*, and clicking flips them.
- `workspace/root_path.py`: `relativize_all_paths()` and the new `absolutize_all_paths()` both run through one `_convert_all_paths(convert)` helper (panel fields, module bubbles, graph node paths), so the two directions can never drift apart.
- `paths_are_relative()` decides the label from **what is actually in the fields**, not a stored flag — so it stays correct after a JSON load, Initialize Project, or the user typing a path by hand. The label is refreshed from `set_rig_root`, `load_pipeline_from_file` and `initialize_project`.
- **Storage is unchanged and deliberately so:** the pipeline JSON always saves paths relative to the Rig Root regardless of what the toggle is showing, so a saved pipeline keeps working when the rig folder moves. The tooltip says this.
- Round-trip verified offline on the blindfold paths: relative → absolute → relative is stable, inline script code and `GRAPH::` ids pass through untouched, and paths outside the root stay absolute in both modes.

### 2026-09-19 — v42.2: browse opens inside the rig; clipboard carries absolute paths
**1. File browsers open in the rig, not the rigs share**
- `SortablePanel.get_start_dir()` order is now: folder of whatever the field points at (existing file *or* a not-yet-created file's parent) → **the project subfolder for this panel type inside the Rig Root** → the Rig Root → `DEFAULT_RIGS_ROOT`.
- New `SortablePanel.TYPE_SUBDIR`: SCRIPT/GLOBAL_SCRIPT→`scripts`, IMPORT_3D/IMPORT_LOD→`model`, JSON/TWEAKER→`skinCluster`, SHAPES/MATERIAL→`controlShape`, PUBLISH→`rig`, MODULE→`guides`. So Browse on a skin panel opens straight in `skinCluster/`.
- The studio rigs share is now a last resort only — landing there means scrolling past every rig in the studio.

**2. Copy/paste between session tabs keeps the file**
- The clipboard (`main_window.clipboard_panel_data`) is shared by every tab, but each tab has its **own** Rig Root — so a relative path copied out of rig A used to resolve against rig B when pasted there, silently pointing at a different (often non-existent) file.
- `copy_panel()` now stores the **absolute** path (`self.path()` / `resolve_path()` for module bubbles; `GRAPH::` ids pass through untouched).
- `paste_panel()` runs it through the **target tab's** `relativize_path()`: pasting into the same rig gives the short path back, pasting into a different rig keeps it absolute so it still points at the original file.
- Verified offline across two rig roots, including `GRAPH::` bubble ids and inline script code.

### 2026-09-19 — v42.3: Load JSON Pipeline opened on another artist's E: drive
- Symptom: "Load JSON Pipeline" opened at `E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\My_Temp`.
- The dialog wasn't the problem — it starts at the **PUBLISH panel's folder**, which is correct. The problem was §5 item 1 from the first review, finally biting: `setup_default_panels()` seeded every new session with hardcoded absolute paths on one artist's E: drive, including `PUBLISH PATH`. So a fresh session pointed the loader there.
- Fixes:
  - `setup_default_panels()` now delegates to `_create_default_project_panels()` — the same project-relative list Initialize Project uses (`workspace/project_init.py::DEFAULT_PANELS`), so there is one source of truth. Added a `CUSTOM SCRIPT` row to that list to match how the real pipelines are laid out. **No hardcoded personal paths remain anywhere in the codebase** (verified by grep).
  - `browse_pipeline_json()` now only trusts the publish dir if it **exists on this machine**; otherwise it falls back to `default_browse_dir()` (Rig Root → rigs share). That also covers loading a pipeline JSON authored on someone else's drive.

### 2026-09-19 — Stage 45 (v42.4): full default panel stack + RUN works on an OFF panel
**1. Default stack now matches a real production pipeline** (taken from `horseRath_a_rig_A_A_v001.json`). `workspace/project_init.py::DEFAULT_PANELS` is now 12 rows of `(title, type, value, active)`, with `{rig}` substituted from the rig name:

| # | panel | type | value |
|---|---|---|---|
| 1 | MAYA GLOBAL SCRIPT | GLOBAL_SCRIPT | — |
| 2 | LOAD SCRIPT PANEL | SCRIPT | `scripts/utils.py` |
| 3 | LOAD MODEL (.ma file) | IMPORT_3D | `model/export.abc` |
| 4 | CUSTOM SCRIPT | SCRIPT | `organize_and_convert_lod("{rig}", delete_ai_lod=True)` |
| 5 | LOAD MODULE | MODULE | (bubbles) |
| 6 | Load_Guide | SCRIPT **off** | `io.import_guide_template(os.path.join(RIG_ROOT, "guides", "{rig}.sgt"))` |
| 7 | Export_Guide | SCRIPT **off** | `io.export_guide_template(...)` |
| 8 | LOAD SKINCLUSTER | JSON | `skinCluster/skinCluster.jSkin` |
| 9 | CONTROL SHAPES | SHAPES | `controlShape/controlShapes.json` |
| 10 | CUSTOM SCRIPT | SCRIPT | `cmds.parent("rig", "{rig}")` + `jnt_vis 0` |
| 11 | Display Switch | SCRIPT | the enum-attr → `*_a_geo` overrideDisplayType script |
| 12 | PUBLISH PATH | PUBLISH | `.` (the rig root — matches the JSON; supersedes the earlier `rig` guess) |

- The two guide panels build their paths from **`RIG_ROOT`** (injected into the shared namespace by `run_script`) rather than the hardcoded absolute paths they were copied from, so they survive the rig folder being moved or renamed.
- `{rig}` comes from the rig name given to Initialize Project; on a brand-new empty session it is `**`, a visible placeholder.
- Folder names follow the parshuram_a listing (`skinCluster/`, `controlShape/`), not the older potli_a JSON (`skin/`, `ctrls/`).
- Verified offline: the rendered stack and that every generated inline script compiles.

**2. An OFF panel's RUN button now works**
- `execute(progress_ui=None, force=False)` on `SortablePanel`, `SortableBubblePanel` (and `execute_single_module`) and `LodLoaderPanel`. The full build still passes `force=False`, so an unchecked panel is skipped exactly as before; clicking RUN/LOAD passes `force=True` and runs it once by hand.
- The button stays enabled and gains a tooltip while off: *"This panel is OFF — the full build skips it. Clicking RUN still executes it, once, by hand."*
- This is what makes the Load_Guide / Export_Guide panels useful: they ship off so the build ignores them, and are run on demand.

### 2026-09-19 — v42.5: "Rig Sets" default panel
- Added a **Rig Sets** SCRIPT panel as row 12, immediately **before PUBLISH PATH** — the sets have to exist before the scene is saved/published.
- The script is the user's own `organize_rig_sets()`, stored **verbatim** so it matches what they have already tested: creates `rigMain_controls_SET`, `rigMain_out_SET`, `rigMain_skeletonMesh_SET`, `rigMain_skeletonAnim_SET`, `rigMain`, then fills them from `*ctl`, `geo*`, `*geo`, all joints, and `char_*_a` using `forceElement`.
- **Brace-safety fix (would have been a crash):** that script contains its own `"{}"` `.format()` placeholders. The panel builder used to call `.format(rig=rig)` on every default value, which raises `IndexError: Replacement index 0 out of range` on this one. `_create_default_project_panels()` now only substitutes when the value actually contains a `{rig}` token. Verified both ways offline.
- Observation, deliberately NOT changed: inside that script the local variables `skeleton_anim_set` / `skeleton_mesh_set` hold the *opposite* set names (`..._skeletonMesh_SET` / `..._skeletonAnim_SET`). The resulting membership is still sensible — meshes end up in the Mesh set, joints in the Anim set — so behaviour is right and only the variable names read oddly. Left verbatim; say the word to rename them.

### 2026-09-19 — Stage 46 (v43.0): AYON reviewable (QC) as a third publish product
**What was already there** (worth knowing before changing it): `dialogs/ayon_publish.py` already published **rigMain** (`product_type: rig`, the built .ma) and **workfileRigging** (`product_type: workfile`, the extracted work folder + re-pathed pipeline JSON), with an optional full rebuild + scene save first. That part of the request was done; only the reviewable was missing.

**New: product 3 — `reviewRigging` (`product_type: review`)**
- UI row in the Products section: checkbox + editable product name, a kind combo (**QC Movie (playblast)** / **Image (still)**), a path field, Browse, and **🎬 Make QC Now**.
- `Make QC Now` runs a playblast with the Playblast tab's current settings and fills the path. To avoid duplicating that logic, `pb_create_clicked()` was split: the new `SessionWorkspace.pb_run_playblast()` gathers the fields and returns `(ok, err, out_path)`; the button handler keeps the popups/preview, the dialog just takes the path.
- Empty path → falls back to the **newest matching file** in the rig's `playblasts/` folder (movies or images depending on the kind).
- The QC file is resolved and validated **before** anything is written to the server, so a missing file aborts the publish rather than leaving it half-done.
- `_publish_review()` copies the media to the publish path, registers a representation **tagged `review`**, and then calls **`ayon_api.upload_reviewable(project, version_id, path, label=...)`** so it plays in the AYON web player. Both steps are guarded: an ayon_api without `upload_reviewable` (older builds), or a failed upload, warns but does not undo an already-registered publish.
- AYON does **not** transcode on upload — H.264 MP4 (yuv420p) is the safe format, which is what the Playblast tab produces when FFmpeg is present. Noted in the code.
- `_attach_representation()` gained a `tags` parameter (passed through to the REST call); the rig and workfile products are unchanged.

**Also:** `get_playblast_dir()` now prefers `<Rig Root>/playblasts` (the folder Initialize Project creates) and only falls back to "beside the session JSON" when there is no Rig Root.

**Unverified** — none of the AYON calls can be exercised from here: the reviewable upload, the `tags` field on the representation POST, and `review` product/version creation all need a live server test.

### 2026-09-19 — v43.1: publish work-folder scan didn't resolve relative paths
- Symptom: the AYON publish dialog's "Rigging Work Folder" list showed every file as `⚠️ … — missing, skipped`, even though they all exist. Only the graph guide JSON (still an absolute `C:/Users/sid2/…` path) was found — which is the tell.
- Cause: Stage 41 made the pipeline JSON store paths **relative** to the Rig Root. `refresh_package_files()` and `_extract_work_folder()` both take their paths straight from that JSON via `collect_json_file_paths()` and call `os.path.isfile()` on them unresolved. A relative path is tested against Maya's CWD, so nothing is ever found — and the extraction would have published an **empty work folder** without erroring.
- Fix: new `AyonPublishDialog._abs()` wraps `workspace.resolve_path()`; used by both the preview and the extractor. The preview tooltip now shows the resolved path plus the stored spelling when they differ.
- **Subtle second half:** `_extract_work_folder` builds `path_mapping` used by `replace_json_file_paths()` to re-path the published JSON, and that matches on the *exact string in the JSON*. Keying the map only by the absolute path would have copied the files correctly but left the published JSON pointing at the old locations. The map is now keyed by **both** spellings.
- Same bug swept from `dialogs/path_tools.py` (Replace All Paths / Create Folder Structure): `_autofill`, `_guess_old_prefix` and `_replace_paths` resolved nothing, so the tool silently did nothing. They now match on the absolute path and write back through `relativize_path()` so fields keep the tab's display style.
- `get_publishable_files()` was already correct (patched in Stage 41).
- Verified offline: 5/5 in-rig files found where all 6 previously reported missing, and the rewrite map matches the JSON's own relative string.

### 2026-09-19 — v43.2: publish dialog — asset search, rigMain gate, image reviewable, per-product publish
1. **Asset (folder) search did nothing.** `cmb_folder` was an editable QComboBox, whose *default* completer matches from the **start** of the string and is case-sensitive. The values are full paths (`/assets/characters/pole_a`), so typing an asset name never matched. Added a `QCompleter` with `MatchContains` + `CaseInsensitive` + `PopupCompletion`, fed from the same folder list (and a count is printed on load).

2. **`rigMain` set is now required for the rig product.** ayon-maya derives a rig product's contents from an objectSet named after it. New `_ensure_rig_set(name)`: creates the set if missing, and if it is empty fills it the way the "Rig Sets" panel does (`char_*_a`, else a top-level `rig`/asset group). If nothing can go in it, the **rig product is skipped** with a clear message — the other products still publish.
   - **Ordering matters:** this runs as *Step 3b*, **before** the scene is saved (Step 4). The set has to be inside the saved `.ma`; doing it at publish time would have written the file first and been useless.

3. **Image reviewable never uploaded (movies worked).** `upload_reviewable()` was called without `content_type`, leaving the server to infer one — fine for `.mp4`, not for stills. Now sends an explicit MIME type from `mimetypes`, falling back to a small `REVIEW_MIME` map (`mimetypes` has no `.webp` entry on some Python builds), plus `filename=`. An unknown extension warns instead of guessing wrong, and the type being sent is printed.

4. **Publish one product at a time.** The three checkboxes were already independent, but nothing made that obvious. Added a **Quick select** row: `Rig only` / `Work folder only` / `Review only` / `All`. (The `.ma` save was already gated on the rig checkbox, so a work-folder-only publish doesn't touch the scene — untick "Rebuild scene" too and it publishes what is on disk.)

**Still unverified against a live server:** the reviewable upload (both kinds), the representation `tags` field, and `review` product creation.

### 2026-09-21 — v43.3: the rig SET is a gate, not something to create
- Correction to v43.2: `_ensure_rig_set()` **created and populated** the set when missing. Wrong — the set is the rigger's statement of what the rig *is*; inventing one at publish time would ship whatever happened to match a `char_*_a` wildcard.
- Replaced with **`_validate_rig_set(prod_name)`** → `(ok, set_name)`. It creates nothing. The rig product publishes only when an objectSet is already in the scene, and:
  - it must be a real **objectSet** — a transform *group* of the same name is rejected explicitly (`'rigMain' exists but is a transform, not a SET`), since ayon-maya will not read a group as a product definition;
  - it must have members — an empty set is rejected;
  - it looks for the product name first, then falls back to `rigMain`, and the warning lists everything it tried and why each failed.
- Still runs as **Step 3b, before the scene is saved**, so a scene that isn't ready is never written or published. If the rig was the only selected product, the whole publish aborts; otherwise the work folder / review still go.
- KRT's own "Rig Sets" default panel creates `rigMain` during the build, so the normal flow passes. A failure here means that step didn't run.
- Decision table verified offline (set with members → publish; group / empty set / missing → refuse; custom product name resolves to its own set or falls back to `rigMain`).

### 2026-09-21 — v43.4: AYON-native rig sets + automatic asset/task selection
**1. "Rig Sets" panel now goes through AYON's own creator.**
- Root cause of "our manual sets are not detected by the AYON publisher": the publisher looks for an **instance node** carrying AYON attributes (creator identifier, product type/name, folder, task), not an objectSet with the right name. A hand-made `cmds.sets(name="rigMain")` has none of those.
- ayon-maya's `CreateRig` (`identifier = "io.openpype.creators.maya.rig"`, `product_type = "rig"`) creates the instance node **and** puts four companion sets inside it: `<product>_controls_SET`, `_out_SET`, `_skeletonAnim_SET`, `_skeletonMesh_SET` — the same layout the old script built by hand.
- The panel script now calls `CreateContext(registered_host()).create("io.openpype.creators.maya.rig", "Main", pre_create_data={"use_selection": False})` + `save_changes()`, reuses an existing instance if one is there, then finds the four child sets by suffix and fills them with KRT's rules: `*ctl` → controls, `geo*` → out, `*geo` → skeletonMesh, all joints → skeletonAnim, `char_*_a` → the instance node.
- If `ayon_core` can't be imported or no host is registered it **creates nothing** and says why — plain sets would just reproduce the original problem.
- `_validate_rig_set()` additionally warns when the set exists but has no `creator_identifier` attribute: KRT will still publish it, but the official Publisher won't list it.

**2. Asset folder and task are selected automatically.**
- `_asset_name_guess()` strips a trailing `_rig` from the Rig Name (`pole_a_rig` → `pole_a`), falling back to the Rig Root folder name.
- `_auto_select_folder()` matches the AYON folder by leaf name — exact, then prefix, then contains — and logs what it chose, or that nothing matched.
- `_auto_select_task()` defaults the task to **`rigging`** (`DEFAULT_TASK`) when the folder has one, exact match first then substring.
- Verified offline against a sample folder tree.

**Unverified:** every AYON call here needs a live session — creator identifier availability, `CreateContext.create()` arguments in the installed ayon-core, and whether the four sets come back as direct members of the instance node.

### 2026-09-21 — v43.5: Save Control Shapes (Overwrite) never overwrote
- Symptom: "Save Shapes (Overwrite)" did nothing visible; "Save Shapes (New Version)" worked.
- Cause: `utils/control_shapes.py::export_control_shapes()` called `get_versioned_path(file_path, get_latest=False)` **itself** and wrote to the bumped path, ignoring the path it was handed. So:
  - *Overwrite* → panel passes `controlShapes.json`, exporter writes `controlShapes_v002.json`; the file the user meant to overwrite is untouched (and the panel field still points at it).
  - *New Version* → panel computes `_v002`, exporter bumps that to `_v003`; a file appears, so it looked like it worked — it was just silently skipping a version number.
- `utils/materials.py::export_material_data()` had the identical bug. Skin export never versioned internally, which is why only shapes were reported.
- Fix: both exporters now write **exactly** where told and return that path; versioning stays the caller's decision (`SortablePanel.save_versioned_data()` already makes it). The panel sets its field from the **returned** path so the field can't drift from what is on disk, and a shapes export that matches nothing now reports an error instead of claiming success.
- **Matching change on load:** `import_control_shapes()` / `import_material_data()` used `get_versioned_path(get_latest=True)`, which prefers the highest `_vNNN`. Left alone, a real overwrite of `controlShapes.json` would be ignored at load time in favour of an older `_v001` — a half-fix. They now use the exact path when it exists and only fall back to the newest version when it doesn't.
- Verified offline against the real `get_versioned_path`: old vs new behaviour for both save modes and the load-back.

### 2026-09-23 — v43.6: script panels can share their namespace with Maya
- Question: after LOAD SCRIPT PANEL runs `utils.py`, typing `UniUtils` in the Script Editor gives `NameError`. Nothing is wrong with `utils.py`.
- Mechanism: `run_script()` does `exec(code, self.shared_namespace)` — a dict **private to this KRT session tab**. Maya's Script Editor evaluates in `__main__`. Two different namespaces, so the import the panel made is invisible there (KRT's own later SCRIPT panels see it fine, which is why the pipeline works).
- **New 🌐 checkbox** on SCRIPT panels (beside the Function field): after the script runs, `publish_namespace_to_maya()` copies every non-dunder name from the shared namespace into `__main__`, so the Script Editor sees exactly what the panel set up. Opt-in per panel, persisted in the pipeline JSON as `share_global`, and carried through copy/paste, duplicate and undo.
- Initialize Project now ticks it on the **LOAD SCRIPT PANEL** row by default — a helper library you can't call from the Script Editor is half a helper.
- **Bug found while here:** `run_script_global()` (the "MAYA GLOBAL SCRIPT" panel) wrote only to `__main__` and never back to `shared_namespace`. So moving a helper library to a Global panel put it in Maya's namespace but *removed* it from KRT's — the next CUSTOM SCRIPT panel calling one of its functions died with `NameError`. A global script is meant to be a superset, not a separate island; it now mirrors back via `_mirror_maya_globals_into_shared()`.
- Mechanism demonstrated offline (isolation → NameError; publish → visible; global-without-mirror → later panels broken; with mirror → fine).
