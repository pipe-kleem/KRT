# -*- coding: utf-8 -*-
"""
Shape Replacer Tool
====================================================================
Pure-Python (maya.cmds) re-implementation of the "Shape Replacer"
(shpRplc) proc extracted from the original RG Toolset MEL script.

WORKFLOW
--------
You have many rig instances in the scene, each on its own namespace
(CharA:, CharB:, CharC: ...), and a single reference file containing
"master" control shapes, all living under ONE shared namespace
(e.g. SRC:).

  1. Select your TARGET controls (across as many namespaces as you
     like) and click "Load Selected -> Targets".
  2. Select the SOURCE controls from the single reference file and
     click "Load Selected -> Sources".
  3. Click RUN.

The tool strips the namespace off every name in both lists and pairs
each target with the source that shares the same base name
(e.g. "CharA:handCtrl" matches "SRC:handCtrl" via the shared base
"handCtrl"). No manual pairing needed, and it doesn't matter how many
different namespaces the targets use.

Run in Maya's Script Editor (Python tab):
    import shape_replacer
    shape_replacer.show()
"""

import maya.cmds as cmds
from collections import defaultdict

WINDOW_NAME = "shapeReplacerWin"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def _strip_namespace(name):
    """'|grp|CharA:handCtrl' -> 'handCtrl'"""
    short = name.split("|")[-1]
    return short.split(":")[-1]


def _get_shapes(node):
    return cmds.listRelatives(
        node, allDescendents=True, shapes=True, fullPath=True, noIntermediate=True
    ) or []


def replace_shapes(targets, source):
    """
    Replace the shape node(s) under every node in `targets` with fresh
    duplicates of the shape node(s) found under `source`. `source` is
    left completely untouched so it can be reused for the next batch.
    Returns how many targets were successfully processed.
    """
    targets = [t for t in targets if cmds.objExists(t)]
    if not targets:
        return 0

    src_shapes = _get_shapes(source)
    if not src_shapes:
        cmds.warning('Source "%s" has no shape nodes -- skipped.' % source)
        return 0

    # Park the source's shape(s) under a throwaway group (as an instance,
    # so the original source keeps its own shapes too) purely so we have
    # something cheap to duplicate once per target.
    temp_grp = cmds.group(empty=True, name="tempShapeGrp#")
    for shp in src_shapes:
        cmds.parent(shp, temp_grp, add=True, shape=True)

    done = 0
    for tgt in targets:
        dup = cmds.duplicate(temp_grp)[0]
        new_shapes = _get_shapes(dup)
        old_shapes = _get_shapes(tgt)

        for nshp in new_shapes:
            cmds.parent(nshp, tgt, add=True, shape=True)

        for oshp in old_shapes:
            if cmds.objExists(oshp):
                cmds.delete(oshp)

        cmds.delete(dup)

        # Rename to <targetName>Shape / <targetName>Shape1, Shape2... for multi-shape controls
        base = tgt.split("|")[-1]
        current_shapes = _get_shapes(tgt)
        for i, shp in enumerate(current_shapes):
            new_name = base + "Shape" if len(current_shapes) == 1 else "%sShape%d" % (base, i + 1)
            if cmds.objExists(shp) and shp.split("|")[-1] != new_name:
                cmds.rename(shp, new_name)

        done += 1

    cmds.delete(temp_grp)
    return done


def run_replace(target_names, source_names):
    """
    Match every target to a source by namespace-stripped base name and
    replace shapes in batches (one duplication pass per unique source).
    Returns a human-readable report string.
    """
    targets = [t.strip() for t in target_names if t.strip()]
    sources = [s.strip() for s in source_names if s.strip()]

    missing_targets = [t for t in targets if not cmds.objExists(t)]
    missing_sources = [s for s in sources if not cmds.objExists(s)]
    targets = [t for t in targets if cmds.objExists(t)]
    sources = [s for s in sources if cmds.objExists(s)]

    src_by_base = {}
    dup_bases = set()
    for s in sources:
        key = _strip_namespace(s)
        if key in src_by_base:
            dup_bases.add(key)
            continue
        src_by_base[key] = s

    targets_by_base = defaultdict(list)
    for t in targets:
        targets_by_base[_strip_namespace(t)].append(t)

    lines = []
    total = 0
    unmatched = []
    for base, tgt_group in targets_by_base.items():
        src = src_by_base.get(base)
        if not src:
            unmatched.extend(tgt_group)
            continue
        n = replace_shapes(tgt_group, src)
        total += n
        lines.append('"%s"  ->  %d target(s) matched to source "%s"' % (base, n, src))

    lines.append("")
    lines.append("Total shapes replaced: %d" % total)

    if unmatched:
        lines.append("")
        lines.append("Unmatched targets (no source shares this base name): %d" % len(unmatched))
        lines.extend("   - " + u for u in unmatched)
    if missing_targets:
        lines.append("")
        lines.append("Target names that don't exist in the scene: %d" % len(missing_targets))
        lines.extend("   - " + m for m in missing_targets)
    if missing_sources:
        lines.append("")
        lines.append("Source names that don't exist in the scene: %d" % len(missing_sources))
        lines.extend("   - " + m for m in missing_sources)
    if dup_bases:
        lines.append("")
        lines.append("Multiple sources shared a base name (only the first found was used): %s"
                      % ", ".join(sorted(dup_bases)))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def _load_selection(field):
    sel = cmds.ls(selection=True, long=True) or []
    if not sel:
        cmds.warning("Nothing selected.")
        return
    existing = cmds.scrollField(field, query=True, text=True)
    existing_lines = [l for l in existing.split("\n") if l.strip()]
    combined = existing_lines + [s for s in sel if s not in existing_lines]
    cmds.scrollField(field, edit=True, text="\n".join(combined))


def _do_run(target_field, source_field, log_field):
    targets = cmds.scrollField(target_field, query=True, text=True).split("\n")
    sources = cmds.scrollField(source_field, query=True, text=True).split("\n")

    cmds.undoInfo(openChunk=True)
    try:
        report = run_replace(targets, sources)
    finally:
        cmds.undoInfo(closeChunk=True)

    cmds.scrollField(log_field, edit=True, text=report)
    print(report)


def show():
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    cmds.window(WINDOW_NAME, title="Shape Replacer", widthHeight=(380, 560), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 8))

    cmds.text(label=" ")
    cmds.text(label="TARGETS   (many namespaces)", align="left", font="boldLabelFont")
    target_field = cmds.scrollField(editable=True, wordWrap=False, height=120)
    cmds.button(label="Load Selected -> Targets",
                command=lambda *_: _load_selection(target_field))

    cmds.text(label=" ")
    cmds.text(label="SOURCE CONTROLS   (single shared namespace)", align="left", font="boldLabelFont")
    source_field = cmds.scrollField(editable=True, wordWrap=False, height=120)
    cmds.button(label="Load Selected -> Sources",
                command=lambda *_: _load_selection(source_field))

    cmds.text(label=" ")
    cmds.text(label="LOG", align="left", font="boldLabelFont")
    log_field = cmds.scrollField(editable=False, wordWrap=True, height=140)

    cmds.text(label=" ")
    cmds.button(
        label="RUN",
        height=38,
        backgroundColor=(0.3, 0.55, 0.3),
        command=lambda *_: _do_run(target_field, source_field, log_field),
    )
    cmds.text(label=" ")

    cmds.showWindow(WINDOW_NAME)


if __name__ == "__main__":
    show()