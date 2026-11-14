"""Reference in / reference out without leaving rubbish (Stage 61).

Shared by joint_transfer and finger_fix. `state` is the caller's own dict:
load() stores the top-level nodes from before the reference arrived, so
remove() can tell OUR leftovers from the user's nodes.

Why the cleanup exists: any node created in this scene under a referenced
node (e.g. the '...ShapeOrig' a blendShape adds under a referenced mesh)
has nowhere to go when the reference is removed, so Maya parks it under
'<ns>RNfosterParent1' or a new 'transformN'.
"""
import os
import re

import maya.cmds as cmds


def find(ns):
    for ref_file in cmds.file(query=True, reference=True) or []:
        try:
            if cmds.referenceQuery(ref_file, namespace=True).lstrip(":") == ns:
                return ref_file
        except RuntimeError:
            continue
    return None


def load(path, ns, state, log=print):
    existing = find(ns)
    if existing:
        log("reference already loaded: " + existing)
        return existing
    if not os.path.isfile(path):
        raise IOError("Reference file not found: " + path)
    state["assemblies_before"] = set(cmds.ls(assemblies=True) or [])
    cmds.file(path, reference=True, namespace=ns)
    log("referenced {} as '{}'".format(path, ns))
    return find(ns)


def _strays(ref):
    """Scene (non-referenced) nodes sitting anywhere under the reference's DAG."""
    ref_nodes = cmds.referenceQuery(ref, nodes=True, dagPath=True) or []
    dag = cmds.ls(ref_nodes, dag=True, long=True) or []        # + all descendants
    return [n for n in dag if cmds.objExists(n)
            and not cmds.referenceQuery(n, isNodeReferenced=True)]


def _only_leftovers(top):
    """True if `top` holds nothing real: no joints, no visible shapes."""
    for d in cmds.listRelatives(top, allDescendents=True, fullPath=True) or []:
        nt = cmds.nodeType(d)
        if nt == "joint":
            return False
        if nt in ("mesh", "nurbsCurve", "nurbsSurface") and not cmds.getAttr(d + ".intermediateObject"):
            return False
    return True


def _leftovers(ns, before):
    junk = []
    for top in cmds.ls(assemblies=True) or []:
        if cmds.referenceQuery(top, isNodeReferenced=True):
            continue
        is_foster = top.startswith(ns) and "RNfosterParent" in top
        is_new_transform = (re.match(r"^transform\d+$", top)
                            and (before is None or top not in before))
        if (is_foster or is_new_transform) and _only_leftovers(top):
            junk.append(top)
    junk += [n for n in cmds.ls(ns + "RNfosterParent*") or [] if n not in junk]
    return junk


def remove(ns, state, delete_first=(), log=print):
    """delete_first: scene nodes to delete before the reference goes
    (e.g. a blendShape that deforms a referenced mesh)."""
    for n in delete_first:
        if cmds.objExists(n):
            cmds.delete(n)
    ref = find(ns)
    strays = []
    if ref:
        strays = _strays(ref)
        if strays:
            cmds.delete(strays)
        cmds.file(ref, removeReference=True)
    else:
        log("no reference with namespace '{}' - only cleaning leftovers".format(ns))
    junk = _leftovers(ns, state.get("assemblies_before"))
    if junk:
        cmds.delete(junk)
    state.pop("assemblies_before", None)
    log("removed reference '{}'; {} stray node(s); leftovers: {}".format(
        ns, len(strays), ", ".join(junk) or "none"))
