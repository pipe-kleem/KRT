# KRT (Kleem Rigging Tool) — AI Handoff Document

This document exists so a **new AI session with no memory of prior work** can pick up development on KRT immediately, without re-deriving context. Read this first, then read `claude/krt-pipeline-status.md` (same project) for the full stage-by-stage history and every implementation detail.

---

## 1. What KRT is

KRT is a PySide/Maya rig-building pipeline tool: a biped/creature module-based pipeline built on top of mGear's Shifter component system. It has two main surfaces:

- **Rig Build Workspace** (`workspace.py` + `widgets.py`) — a linear panel-stack UI. Each "LOD" is an ordered stack of panels (Script, Import 3D, Skin JSON, Control Shapes, Publish Path, Module Bubbles, Tweaker, LOD Loader, Global Script, etc.), run top-to-bottom.
- **Module Graph Editor** (`graph.py`) — a separate node-graph UI where each node represents an mGear Shifter component guide (or a Plebe biped template, a Custom `.sgt` module, or a guide-less Custom Script node), wired together to define parent/child guide relationships, then built into a real Maya rig via mGear's Shifter API.

## 2. Where everything lives

- **KRT source**: `C:\Pipeline\KRT` on the user's machine (device name "kl201"). Files: `main.py`, `workspace.py`, `widgets.py`, `graph.py`, `session.py`, `utils.py`, `compat.py`, `dialogs.py`, plus `PanelScripts/Tweaker.py`.
- **mGear reference source** (read-only, for looking up real Shifter behavior): `C:\Users\vishal3\Documents\maya\modules\scripts\mgear` — note this may be a customized/forked mGear (it has features, e.g. a "Blueprint" mechanism, not present in stock mGear on some attribute lookups).
- **This claude.ai Project** ("3dMayaRigPipeline") holds the persistent status doc: `claude/krt-pipeline-status.md`. That file is the authoritative, continuously-updated log of every stage of work — architecture notes per file, full feature write-ups with the user's verbatim requests, known caveats, and a running "next possible work" list. **Always read it before starting new work**, and **always update it (full-content replace, no in-place patch) after finishing a stage.**

## 3. Environment / tooling reality

- Development happens in a cloud sandbox with **no Maya installed**. Nothing gets tested live by the AI — every change is verified only by `python3 -m py_compile` and a duplicate-method AST scan, never by running it. This is repeated in nearly every stage's caveats for a reason: it is real and permanent, not a one-off gap.
- The user's machine is reached via a remote-devices file bridge (`mcp__remote-devices__*` tools): `get_device_info`, `device_list_dir`, `device_stage_files`, `device_commit_files`, `device_request_folder_access`. A `device_bash` (shell on the user's machine) tool may or may not be present in a given session — check with `ToolSearch` before assuming it's there. When absent, all file editing must happen by staging files into the cloud sandbox, editing them there, and committing them back.
- Connected folders at minimum: `C:\Pipeline\KRT`. mGear source access (`...\mgear\core`, `...\mgear\shifter`) may need `device_request_folder_access` if not already granted.
- Maya caches imported Python modules in memory. **Overwriting a `.py` file on disk has no effect on an already-running KRT session until Maya is restarted or the module is explicitly reloaded.** This has caused at least one false "fix didn't work" report (Stage 25) — always ask the user to confirm a full Maya restart before treating a re-reported bug as a real regression in the delivered code.

## 4. Delivery workflow (follow this exactly for every change)

1. Edit the relevant file(s) in the cloud workspace (typically staged at `/mnt/user-data/uploads/KRT/...` from a prior stage, or freshly staged via `device_stage_files`).
2. `python3 -m py_compile <changed files>` — must be clean.
3. Run an AST-based duplicate-method scan across `widgets.py`/`workspace.py`/`graph.py`/`dialogs.py` — must produce no output (a stray duplicate method definition silently shadows the real one and is an easy mistake with iterative `Edit` calls).
4. `SendUserFile` on each changed file to get a `file_uuid`.
5. Fresh `device_list_dir` on `C:\Pipeline\KRT` immediately before committing, to get the current on-disk mtime for each file.
6. `device_commit_files` with `expectedMtimeMs` set from step 5 for every file (the mtime guard prevents silently clobbering a newer edit the user made directly on their machine).
7. Update `claude/krt-pipeline-status.md`: read it, then `project_write` the FULL updated content back (there is no in-place patch — every update replaces the whole doc). Add a new "### Stage N" section under Features, update the relevant Architecture bullets, add any new Known Caveats and Next-possible-work items.
8. Report back to the user in plain conversational language — what changed, and the standing "not tested live in Maya yet" caveat, plus anything that was inferred rather than confirmed from source (flag it explicitly, as with Stage 27's `useIndex`/`parentJointIndex` defaults).

Scratch files for doc updates go in a throwaway subdirectory (e.g. `docwork/`) and get `rm -rf`'d after the `project_write` succeeds — don't leave scratch files lying around.

## 5. Working conventions with this user

- The user reports work in numbered "Stages" — one user message, one or more numbered requests, worked through to full completion (code + delivery + doc) before moving on.
- **Always quote the user's request verbatim** in the status doc's stage write-up — this has been done consistently for every stage and is expected to continue. It keeps the historical record honest about what was actually asked versus how it was interpreted.
- When the exact mGear behavior/attribute mapping isn't already known, **read mGear's own source directly off the user's machine** via the device bridge rather than guessing — this has repeatedly produced correct, confirmed implementations (e.g. Stage 27's Main Settings fields, sourced from `mgear/shifter/component/guide.py`'s `componentMainSettings` class). If something can't be confirmed (like an `addParam()` default not found after an exhaustive search), implement a reasonable inference AND explicitly flag it as unconfirmed in the caveats — don't silently guess.
- The user often follows up with screenshots of Maya/mGear's own UI as the spec for what a KRT feature should look like or expose — treat these as authoritative references, not just illustrations.
- No git operations have occurred in this workflow so far (delivery is direct-to-device-file, not via a repo) — if that ever changes, note the commit/PR attribution requirements are: commits end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` and a `Claude-Session:` link; PRs end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)` and the same link. Get the current session's exact values from the active system reminder rather than reusing an old one verbatim.

## 6. Current state (as of Stage 27, 2026-09-07)

All 27 stages are implemented, delivered to `C:\Pipeline\KRT`, and documented. Headline items from the most recent stages:

- **Stage 26**: searchable "Attach Under" combo in the graph Node tab; new guide-less "Custom Script Module" node type.
- **Stage 27**: mGear's own per-component "Main Settings" (Component Index, Connector, Joint Settings, Channels Host, Custom Controllers Group, Color Settings) mirrored directly into the graph Node tab for real Shifter components, live-applying to an already-built guide with no rebuild needed; full node-level Copy/Cut/Paste/Duplicate in the graph editor (right-click menu + Ctrl+C/X/V).

**Top priority open item**: none of Stage 24 through 27 has been verified in a live Maya session yet. Stage 27 specifically has one flagged inference worth double-checking first — `useIndex`/`parentJointIndex` default values (`False`/`-1`) were inferred from a screenshot, not confirmed against mGear's own `addParam()` declaration (which could not be located in the files searched). See `claude/krt-pipeline-status.md`'s "Known caveats" and "Next possible work" sections for the complete, current punch list — it is kept up to date every stage and is more current than anything else that could be written here.

## 7. How to start the next session

1. Read `claude/krt-pipeline-status.md` in full (it's long — that's expected; it's the whole project history).
2. Check `ToolSearch` for `device_bash` availability to know which editing workflow applies.
3. Wait for the user's next numbered Stage request, or a live-Maya test report on prior stages.
4. Follow the delivery workflow in Section 4 above for whatever comes next.
