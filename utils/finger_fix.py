"""Finger Fix - match the CC finger joints to the Hand Build rig (Stage 61).

Headless version of the "Finger Fix" tab (HandRigMatchingUI) of
jointTransferPro2.py. Used by the FINGER FIX panel, or from a script:

    from KRT.utils import finger_fix; finger_fix.run(sides="LR")

Steps (STEPS below):
    0. create_tip_joints   duplicate each <Finger>3 joint as <Finger>4, push it
                           out to the finger tip and parent it under <Finger>3
    1. load_reference      reference Hand_Build_v01.ma (ns Hand_Build_v01)
    2. snap_controls       snap the hand rig's controls onto the CC joints
                           (parentConstraint, then delete the constraint)
    3. match_joints        copy the hand rig's finger joint matrices onto the
                           CC joints; children kept in place; skin preserved
    4. remove_reference    remove the hand rig + any leftovers

sides: "LR" (both), "L" or "R" - the same as the tool's Side Option.
"""
import maya.cmds as cmds

from . import rig_resources, rig_reference, step_runner

HAND_RIG_FILE = rig_resources.resource(rig_resources.HAND_RIG)
NAMESPACE = "Hand_Build_v01"
FINGERS = ("Thumb", "Index", "Mid", "Ring", "Pinky")

# Tip offset in the 3rd joint's object space (the two moves of the original tool).
TIP_OFFSETS = [(1.72445e-07, 4.099654, 4.25303e-07),
               (-0.593984, 3.39368e-08, 9.1113e-10)]

SNAP_PAIRS = [   # (CC joint, hand-rig control) - {S} side, {NS} namespace prefix
    ("CC_Base_{S}_Hand",   "{NS}main_{S}_ctrl"),
    ("CC_Base_{S}_Thumb1", "{NS}CC_Base_{S}_Thumb1_TOP_CTRL"),
    ("CC_Base_{S}_Thumb4", "{NS}CC_Base_{S}_Thumb1_AIM_CTRL"),
    ("CC_Base_{S}_Index1", "{NS}CC_Base_{S}_Index1_TOP_CTRL"),
    ("CC_Base_{S}_Index4", "{NS}CC_Base_{S}_Index1_AIM_CTRL"),
    ("CC_Base_{S}_Mid1",   "{NS}CC_Base_{S}_Mid1_TOP_CTRL"),
    ("CC_Base_{S}_Mid4",   "{NS}CC_Base_{S}_Mid1_AIM_CTRL"),
    ("CC_Base_{S}_Ring1",  "{NS}CC_Base_{S}_Ring1_TOP_CTRL"),
    ("CC_Base_{S}_Ring4",  "{NS}CC_Base_{S}_Ring1_AIM_CTRL"),
    ("CC_Base_{S}_Pinky1", "{NS}CC_Base_{S}_Pinky1_TOP_CTRL"),
    ("CC_Base_{S}_Pinky4", "{NS}CC_Base_{S}_Pinky1_AIM_CTRL"),
]

STEPS = [
    ("create_tip_joints", "0. Create finger tip joints"),
    ("load_reference",    "1. Reference hand rig"),
    ("snap_controls",     "2. Snap controls to joints"),
    ("match_joints",      "3. Match joints (skin kept)"),
    ("remove_reference",  "4. Remove reference + cleanup"),
]

import sys
if not hasattr(sys, "_krt_finger_fix_state"):
    sys._krt_finger_fix_state = {}
_STATE = sys._krt_finger_fix_state


def _log(msg):
    print("[KRT FingerFix] " + msg)


def _sides(sides):
    out = [s for s in "LR" if s in (sides or "LR").upper()]
    return out or ["L", "R"]


def _prefix(ns):
    ns = (ns or "").strip().rstrip(":")
    return ns + ":" if ns else ""


# ── 0. tip joints ────────────────────────────────────────────────────────
def create_tip_joints(sides="LR"):
    """<Finger>3 -> new <Finger>4 at the tip. Skips a finger whose 4 already
    exists, so running the step twice does not stack extra joints."""
    made, skipped = [], []
    cmds.undoInfo(openChunk=True, chunkName="KRT_FingerTipJoints")
    try:
        for s in _sides(sides):
            for f in FINGERS:
                src = "CC_Base_{}_{}3".format(s, f)
                tip = "CC_Base_{}_{}4".format(s, f)
                if not cmds.objExists(src):
                    skipped.append(src + " (missing)")
                    continue
                if cmds.objExists(tip):
                    skipped.append(tip + " (exists)")
                    continue
                # parentOnly: copy just this joint, not anything under it
                dup = cmds.duplicate(src, parentOnly=True, name=tip)[0]
                for offset in TIP_OFFSETS:
                    cmds.move(*offset, dup, relative=True, objectSpace=True, worldSpaceDistance=True)
                cmds.parent(dup, src)
                made.append(tip)
    finally:
        cmds.undoInfo(closeChunk=True)
    _log("created {} tip joint(s)".format(len(made)))
    if skipped:
        _log("skipped: " + ", ".join(skipped))
    return made


# ── 1. reference ─────────────────────────────────────────────────────────
def load_reference(path=None, ns=NAMESPACE):
    return rig_reference.load(path or HAND_RIG_FILE, ns, _STATE, log=_log)


# ── 2. snap controls ─────────────────────────────────────────────────────
def snap_controls(sides="LR", ns=NAMESPACE):
    if not rig_reference.find(ns):
        raise RuntimeError("Hand rig '{}' is not referenced (run step 1 first)".format(ns))
    pre, count, missing = _prefix(ns), 0, []
    for s in _sides(sides):
        for jnt_fmt, ctl_fmt in SNAP_PAIRS:
            jnt, ctl = jnt_fmt.format(S=s), ctl_fmt.format(S=s, NS=pre)
            if cmds.objExists(jnt) and cmds.objExists(ctl):
                cmds.delete(cmds.parentConstraint(jnt, ctl, maintainOffset=False))
                count += 1
            else:
                missing.append("{} -> {}".format(jnt, ctl))
    for m in missing:
        cmds.warning("[KRT FingerFix] skipped missing pair: " + m)
    _log("snapped {} control(s)".format(count))
    if count == 0:
        raise RuntimeError("No control was snapped - check the namespace and step 0 (tip joints)")
    return count


# ── 3. match joints ──────────────────────────────────────────────────────
def _update_bind_pre_matrix(joint):
    conns = cmds.listConnections(joint + ".worldMatrix[0]", type="skinCluster",
                                 connections=True, plugs=True) or []
    for i in range(0, len(conns), 2):
        dst = conns[i + 1]
        if ".matrix[" in dst:
            skin, attr = dst.split(".")
            index = attr.split("[")[1].split("]")[0]
            cmds.setAttr("{}.bindPreMatrix[{}]".format(skin, index),
                         cmds.getAttr(joint + ".worldInverseMatrix[0]"), type="matrix")


def snap_matrix_preserve_mesh(source, target):
    """target takes source's rotateOrder, jointOrient and world matrix; its
    children stay where they are; the skin is told this is the new bind pose."""
    children = cmds.listRelatives(target, children=True, type="transform", fullPath=True) or []
    keep = {c: cmds.xform(c, query=True, worldSpace=True, matrix=True) for c in children}
    cmds.setAttr(target + ".rotateOrder", cmds.getAttr(source + ".rotateOrder"))
    if cmds.objExists(source + ".jointOrient") and cmds.objExists(target + ".jointOrient"):
        cmds.setAttr(target + ".jointOrient", *cmds.getAttr(source + ".jointOrient")[0])
    cmds.xform(target, worldSpace=True, matrix=cmds.xform(source, query=True, worldSpace=True, matrix=True))
    for c, m in keep.items():
        cmds.xform(c, worldSpace=True, matrix=m)
    _update_bind_pre_matrix(target)


def match_joints(sides="LR", ns=NAMESPACE):
    if not rig_reference.find(ns):
        raise RuntimeError("Hand rig '{}' is not referenced (run step 1 first)".format(ns))
    pre, count, missing = _prefix(ns), 0, []
    cmds.undoInfo(openChunk=True, chunkName="KRT_FingerMatch")
    try:
        for s in _sides(sides):
            for f in FINGERS:
                for n in range(1, 5):            # parents before children
                    base = "CC_Base_{}_{}{}".format(s, f, n)
                    src = pre + base
                    if cmds.objExists(src) and cmds.objExists(base):
                        snap_matrix_preserve_mesh(src, base)
                        count += 1
                    else:
                        missing.append(base)
    finally:
        cmds.undoInfo(closeChunk=True)
    if missing:
        cmds.warning("[KRT FingerFix] skipped missing joint pair(s): " + ", ".join(missing))
    _log("matched {} joint(s) (skin preserved)".format(count))
    return count


# ── 4. remove reference ──────────────────────────────────────────────────
def remove_reference(ns=NAMESPACE):
    rig_reference.remove(ns, _STATE, log=_log)


# ── running steps ────────────────────────────────────────────────────────
def run_step(key, ref_path=None, ns=NAMESPACE, sides="LR", **_ignored):
    ns = (ns or NAMESPACE).strip()
    if key == "create_tip_joints":
        return create_tip_joints(sides)
    if key == "load_reference":
        return load_reference(ref_path, ns)
    if key in ("snap_controls", "match_joints"):
        return globals()[key](sides, ns)
    if key == "remove_reference":
        return remove_reference(ns)
    raise KeyError(key)


def run_steps(keys=None, on_step=None, **opts):
    """opts: ref_path, ns, sides. Returns (success, error_text)."""
    return step_runner.run_steps(STEPS, run_step, keys, on_step, opts, _log)


def run(sides="LR", ns=NAMESPACE, ref_path=None):
    ok, err = run_steps(None, sides=sides, ns=ns, ref_path=ref_path)
    if not ok:
        raise RuntimeError(err)
