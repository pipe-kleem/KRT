# KRT (Kleem Rigging Tool) — Handoff Notes

Standalone context dump for a fresh AI session picking up this work. Read this fully before touching anything.

## What this is

KRT = "Kleem Rigging Tool", a PySide/Maya biped & creature rig-building pipeline tool built on top of mGear's Shifter framework. Lives at `C:\Pipeline\KRT` on the user's Windows machine (device name "kl201"), reached through a remote-devices bridge. mGear reference source (for cross-checking behavior, since it can't be run) is at `C:\Users\vishal3\Documents\maya\modules\scripts\mgear`.

There is a claude.ai Project called **"3dMayaRigPipeline"** with a persistent status doc at `claude/krt-pipeline-status.md` — **read that doc first**, it is the authoritative, continuously-updated architecture/feature/caveat reference and is kept current after every stage of work. This handoff file is a supplement covering the *narrative* of how we got here and things worth knowing that aren't naturally doc-shaped.

## Critical constraint — read this before doing anything

**The sandbox this work happens in cannot run Maya.** There is no way to actually execute this code and see if it works. Every single change across every stage has been verified only by:
1. `python3 -m py_compile <file>.py` (syntax correctness)
2. A Python `ast`-based method-count/duplicate-check across the affected classes (structural sanity — nothing silently broke, no duplicate method names)
3. Manual, careful cross-referencing against mGear's actual source code (a partial mirror of it lives under `/mnt/user-data/uploads/mgear/` in this sandbox — only ~11 files, not the full package, so some questions about exact runtime behavior (e.g. PyMEL's `getParent(-1)` semantics on a parentless node) cannot be fully resolved from source alone and have to be reasoned through carefully instead)

**This means every single stage has had at least one thing that seemed complete but turned out not to fully work as expected once the user actually tried it in Maya.** The user's feedback loop has been: I ship something, they try it in a real session, and about half the time something subtly doesn't work as intended — sometimes cosmetic, sometimes a real functional bug I had to root-cause purely by reading mGear source and reasoning about control flow. Do not assume "it compiles and the method inventory looks right" means "it works." State that uncertainty plainly when reporting back, the way I have been.

## Workflow / mechanics for making changes

1. Read the target file(s) with the `Read` tool (files are large — `graph.py` is ~140KB, `widgets.py` ~77KB, `workspace.py` ~72KB — read the relevant sections, not necessarily the whole file, but always read before editing).
2. Make edits with `Edit` (never blind-guess file contents).
3. `python3 -m py_compile <file>.py` after every edit round.
4. AST method-inventory check (a short inline Python script using `ast.walk`) to confirm expected method counts on the classes touched, and to check for accidental duplicate method definitions.
5. `SendUserFile` on the changed file(s).
6. `mcp__remote-devices__device_list_dir` on `C:\Pipeline\KRT` to get **fresh** `mtimeMs` values (required — `device_commit_files` refuses a stale mtime).
7. `mcp__remote-devices__device_commit_files` with the `file_uuid`s from step 5 and the fresh `expectedMtimeMs` from step 6, writing to `C:\Pipeline\KRT\<file>.py`.
8. Update `claude/krt-pipeline-status.md` in the project (`project_read` first, then `project_write` the full updated content back — there is no in-place patch) with what changed, and be honest in the "Known caveats" / "Next possible work" sections about anything unverified or newly-introduced-but-unconfirmed.
9. Report back to the user summarizing what changed, in plain conversational terms (not a wall of bullet points) — they are not a programmer reading a diff, they're a rigger who needs to know what to go try in Maya.

## Codebase map

- **`graph.py`** (~140KB) — the Module Graph Editor. `RigNode` (QGraphicsRectItem) = one mGear Shifter component guide, a Plebe biped node, or a Custom Module (`.sgt` file) node. `RigWire` = the connection between them. `NodeGraphView` (QGraphicsView) hosts the whole canvas and handles all mouse/keyboard interaction. `ModuleGraphWidget` is the QWidget wrapping the view + the right-hand Node tab / Guide Settings tab side panel — this is the class most of the "business logic" methods live on (`build_node_guide`, `_build_plebe_guide`, `_build_custom_sgt_guide`, `serialize_node`/`deserialize_node`, `get_graph_config_data`/`_apply_graph_config_data`, the undo/redo system, etc).
- **`widgets.py`** (~77KB) — the Rig Builder Workspace panels, most importantly `SortableBubblePanel` (the "LOAD MODULE" panel type with module bubbles + a green LOAD button) and `ModuleBubble`.
- **`workspace.py`** (~72KB) — `SessionWorkspace`: the user profile page, sidebar module list, and pipeline JSON save/load.
- **`main.py`** — top-level `KRT_Tool` window.
- **`utils.py`** — shared helpers (`export_control_shapes`/`import_control_shapes`, `find_guide_model`, `apply_control_shapes_library`).
- **`session.py`** — `SessionManager`, persists user notes / recent-modules list / session state.
- **`dialogs.py`** — misc dialog classes (`BuildProgressDialog` etc), not touched much in recent stages.

## Chronological summary of everything done (this session + prior, per the project status doc's stage numbering)

**Stage 10 and earlier** (window sizing, per-bubble and panel-level LOAD button batch build/delete-guide flow) — done, not revisited recently.

**Stage 11** (3 requests): Control Shapes Library field (a `.ma`/`.mb` file of `*_controlBuffer` curves to auto-replace default guide shapes), drag-to-reorder module bubbles within a panel, and Save Guides writing to an auto-named `guide/` subfolder.

**Stage 12** (bugfixes to Stage 11, reported with screenshots): Control Shapes Library wasn't actually firing for Plebe guides (wired into the wrong build path) and was wrongly graph-wide instead of Plebe-only — fixed, scoped per-node, only shown/used for Plebe nodes. Save Guides errored requiring a live scene guide — fixed to be fully scene-independent, reusing the same data path as Export/Import Config JSON.

**Stage 13** (3 requests, with screenshots):
1. "Attach Under" dropdown needed to show the parent's full guide locator hierarchy, not just "(Whole Guide Root)" — turned out the dropdown logic already did this correctly once a guide was *built*; the real gap was no easy way to build just the parent's guide from the Node tab. Added a "⟲ Build Parent's Guide" button next to the dropdown.
2. New "Custom Module (from .sgt file)" node type — lets the user point the search popup at any standalone mGear partial-guide-template `.sgt` file (e.g. a hand-modified stock component) instead of only the catalog component list. New `_build_custom_sgt_guide` method using `mgear.shifter.io.import_partial_guide()`.
3. Multi-select-in-order popup (`GraphNodeOrderDialog` in `widgets.py`) for adding several graph modules into a bubble panel at once, replacing the old one-at-a-time sidebar-select-and-add-from-graph-editor flow.

**Stage 14** (2 requests, most recent, with screenshots — this is what was just completed):
1. **"ctrl Z and ctrl shift z should work for all the things in graph for undo and redo"** — the graph editor had *zero* undo/redo of its own (Maya's native undo only covers actual Maya scene nodes from Build Guides/Build Modules, not the Qt graph widget's own nodes/wires/positions/fields). Implemented a snapshot-stack-based undo/redo on `ModuleGraphWidget` (`_undo_stack`/`_redo_stack`, capped at 60), reusing the existing `get_graph_config_data()`/`_apply_graph_config_data()` round-trip (the same one Save/Load Guides and Export/Import Config already use) rather than hand-writing dozens of individual undo-command classes. Hooked into: node creation (all 3 ways), node/wire deletion, wire connect/disconnect, node position drag (new `RigNode.mousePressEvent`/`mouseReleaseEvent` overrides, snapshot taken on press and dropped again on release if nothing actually moved), and every Node-tab field edit — with rapid edits (e.g. typing) coalesced into one undo step via a "pending" flag reset on selection change. Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y wired into `NodeGraphView.keyPressEvent`, active only while the graph view has keyboard focus (so it doesn't fight a text field's own native undo). **Deliberately does NOT cover actual Maya scene builds** (Build Guides/Build Modules) — those stay on Maya's own `cmds.undoInfo` chunks, since mixing the two systems would let a graph-undo silently desync from real Maya nodes still sitting in the scene.

2. **"attach under on parent is resetting when i am building guides or module. and my custom module still in outside of parented guide, i tried 2-3 times"** — a real, confirmed bug, not a misunderstanding. Root-caused by tracing through `mgear/shifter/guide.py`'s `draw_guide()`: both `build_node_guide` and `_build_custom_sgt_guide` had inlined the exact same fragile pattern — `if attach_target and cmds.objExists(attach_target): use it; else: silently fall back to the parent's whole guide root`. When the stored long-path locator (e.g. `arm_R0_root`) had gone stale — most likely because the parent's guide had been deleted+rebuilt since the locator was chosen (the module-bubble LOAD button's own well-documented guide-auto-deletion behavior is one known way this happens) — `cmds.objExists()` on the stale path returns False, and the code silently built under the bare parent model instead. This *also* explains why the "Attach Under" combo box appeared to "reset" to `(Whole Guide Root)` afterward: it wasn't actually reset by anything, the stored path just no longer matched any entry in the freshly-recomputed locator list, so the UI display defaulted to index 0. **Fix**: extracted a shared `_resolve_attach_parent(node, parent_node, parent_root, pm)` method used by both build paths. It now: (a) uses the exact stored path if it still exists (fast path, unchanged for the common case), (b) if not, tries to re-find a locator with the same *short* name on the parent's current guide and self-heals `node.parent_local_target` to the new path (with a `cmds.warning` explaining why), (c) only if that also fails, falls back to the whole guide root — loudly (`cmds.warning`) and by explicitly clearing the stale stored target, instead of silently building in the wrong place while the UI kept lying about what was selected.

Both Stage 14 fixes were delivered and committed to `C:\Pipeline\KRT\graph.py` and `C:\Pipeline\KRT\workspace.py`. **Neither has been confirmed working by the user in a live Maya session yet** — this is the very next thing that should happen, and if a fresh AI session picks this up, the first thing to do is ask the user how it went, not assume it's settled.

## Open items / what's next

- **Immediate**: confirm with the user that (a) Ctrl+Z/Ctrl+Shift+Z actually undo/redo graph edits as expected in their real session, and (b) a Custom Module node built with a specific "Attach Under" locator chosen now actually nests under that locator instead of the parent's whole root.
- One still-unverified edge case flagged honestly in the status doc: a Custom Module node built with **no** specific Attach Under locator (falling back to the parent's bare guide-model root as `initParent`) relies on an assumption about PyMEL's `getParent(-1)` behavior on a parentless node that couldn't be confirmed from the partial mgear source available here. If this specific case ever throws an error for the user, it's the next thing to dig into — the workaround in the meantime is picking an actual locator via Attach Under rather than leaving it on the whole root.
- See the project status doc's "Next possible work" section for smaller unprompted ideas (an Export Only checkbox for Plebe skin-to-rig, multi-guide-root awareness for the Guide Settings tab, etc.) — none of these have been requested by the user, don't do them unprompted.

## A note on working style that's mattered here

The user is not a programmer — they're a rigger describing UI behavior and bugs, often via screenshots with circles/arrows rather than precise technical language. Read their screenshots carefully; they usually contain the actual root-cause evidence (e.g. an Outliner screenshot showing exactly which Maya node ended up parented where) even when the accompanying text is terse. When something is genuinely uncertain because it can't be tested, say so plainly in both the response to the user and the status doc — this user has caught real bugs specifically *because* past responses didn't oversell confidence, and they've now tried nearly every stage's fix and reported back what actually happened, so the honest-caveat approach is clearly working and should continue.
