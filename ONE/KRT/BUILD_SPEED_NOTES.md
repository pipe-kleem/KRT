# Kleem Rigging Tool — Caching & Build-Speed Notes

## What was added (this pass)

### Per-step caching
Every step row (script, MA, module, skin, shapes, publish) now has three small
buttons next to **RUN/LOAD**:

- **💾 Cache** — saves a full Maya scene snapshot (`.ma`) *after* this step's state.
  Turns green once a cache exists.
- **⏩ Load / Build from cache** — left-click *loads* that snapshot (wipes the scene
  and opens the accumulated result of every step up to and including this one, for
  inspection). Right-click the button (or use the "..." menu) for **"Build from here"**,
  which loads the cache and then continues executing the remaining steps. Enabled only
  when a cache exists.
- **🗑 Remove cache** — deletes this step's cache file. Enabled only when one exists.

Caches are keyed by a stable per-step `uuid` (saved into the pipeline JSON, so caches
survive save/reload). They live in:
`<MayaAppDir>/KleemRiggingTool/step_caches/<uuid>.ma`

### Build behavior (as requested)
A full **BUILD CURRENT LOD** now:
1. Removes all existing step caches for that LOD.
2. Runs from scratch.
3. Writes a fresh cache after each active step.

**Build Till Here** does the same but only up to the target step (it does not wipe
caches beyond the target). A header checkbox **"Cache steps during build"** (on by
default) lets you turn all of this off for a pure, no-I/O build.

### Iteration workflow this enables
After one full build, if you tweak (say) step 40's script, click **⏩ Run from cache**
on step 39, then hit **RUN** on 40, 41 … — you skip re-running steps 0–39 entirely.
When jumping into a cache, the tool re-runs the leading utility-script rows to rebuild
the Python helper namespace (e.g. `utils.py`), so functions like
`organize_and_convert_lod`, `replace_and_rename_mesh`, `repath_textures` are available.

## Speed improvements applied to the build itself
Wrapped every build in a "fast" context that is fully restored afterward:
- **Undo disabled** (`undoInfo(state=False)`) — no undo queue = less memory + faster.
- **Command echo off** (`commandEcho(state=False)`) — your inline scripts fire
  hundreds of `setAttr`/`cmds` calls (muscle poses, addInfluence, tongue clusters);
  echoing each to the Script Editor is a real cost.
- **Viewport refresh suspended** (`refresh(suspend=True)`) during the whole build,
  forced once at the end.

Also added **per-step timing**: after each build the Script Editor prints total time
plus the 5 slowest steps, so you can see where the time actually goes.

## Bugs fixed along the way
- **Skin mesh selection**: `meshes` field was split on `,` without trimming spaces, so
  `"geo_a, geo_b"` tried to select `" geo_b"` (leading space) and silently failed to
  load that skin. Now each name is stripped. Fixed in both skin *import* and *export*.

---

## Deeper optimization ideas (for your review — not yet applied)

1. **Cache as `.mb` instead of `.ma`.** You chose `.ma` (readable/diffable), but a full
   character rig ASCII snapshot can be hundreds of MB and is slow to write/open. Binary
   (`.mb`) caches are typically ~3–5× smaller and faster. One-line change if you want a
   toggle (cache type `mayaBinary`, extension `.mb`). Biggest single speed/disk win for
   the caching feature.

2. **Cache only heavy steps, not all 48.** Writing a snapshot after *every* step adds a
   lot of I/O. The expensive-to-recompute steps are the model import (`.abc`), the skin
   loads, module build, and finalize. A per-row "auto-cache" toggle (cache only rows you
   mark) would keep the safety-net without the full I/O tax.

3. **Localize `R:/` network reads.** Scripts, models and skin files load from
   `R:/Pipeline_Share/...`. On a busy network this dominates. A "sync to local temp on
   first build" step (copy referenced files to a local scratch dir, run from there) can
   cut minutes on cold builds.

4. **Skin import is usually the slowest phase.** mGear `importSkin` is per-vertex work.
   Options: pre-select the exact target meshes (now fixed), store weights as `.mb`
   binary skin, or evaluate ngSkinTools/`deformerWeights` for faster round-trips on the
   body mesh.

5. **Evaluation Manager off during build.** For heavily scripted builds, DG re-eval on
   every attribute change is overhead. Setting `evaluationManager(mode='off')` for the
   build (restored after) can help; needs testing against your muscle/stretch setups
   which may rely on live eval. Left out for now because it's scene-dependent.

6. **Batch the `addInfluence` calls.** `finalize`/`addInfulance` add 60+ fan/muscle
   joints with `lockWeights=True, weight=0`. That's already one call per group — good.
   Ensure `normalizeWeights` is set to `2` (post) once at the end rather than
   recomputing per influence.

7. **Suppress Script Editor result printing.** The muscle-restore block prints hundreds
   of lines. `scriptEditorInfo(suppressResults=True)` during build (kept warnings/errors
   visible) would trim UI overhead. Not applied yet because it's a global UI state.

8. **Run the whole build in one undo chunk / one `refresh`** — already effectively done
   via suspend; a further step is to defer all `cmds.select`/UI syncs to the end.

Use the new per-step timings from a real build to decide which of these is worth it —
they'll tell you whether your time is in skin import, network I/O, or the inline scripts.
