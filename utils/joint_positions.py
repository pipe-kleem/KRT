"""Save / load joint positions (Stage 66) - the JOINT POSITIONS panel.

After JOINT TRANSFER + FINGER FIX (slow, partly manual) the joints are where
they should be: Save writes every joint under the root to a JSON file. A
normal build then just Loads that file instead of re-running the fixes.

Saved per joint (local values, parent-first order): parent, translate,
rotate, jointOrient, rotateOrder, scale, radius.
Load:
  - creates a joint that is missing (e.g. the finger tip joints FINGER FIX
    step 0 adds) under its saved parent,
  - sets the local values parent-first,
  - then updates every skinCluster's bindPreMatrix for the moved joints, so
    the skin does not move (same trick as joint_transfer / finger_fix).
"""
import json
import os

import maya.cmds as cmds

DEFAULT_ROOT = "CC_Base_BoneRoot"
ATTRS = ("translate", "rotate", "jointOrient", "scale")


def _log(msg):
    print("[KRT JointPositions] " + msg)


def _short(node):
    return node.split("|")[-1]


def _one(name):
    found = cmds.ls(name, type="joint", long=True) or []
    if len(found) > 1:
        cmds.warning("[KRT JointPositions] '{}' is not unique - using {}".format(name, found[0]))
    return found[0] if found else None


def joints_under(root=DEFAULT_ROOT):
    root_long = _one(root)
    if not root_long:
        raise RuntimeError("Root joint not found: " + root)
    kids = cmds.listRelatives(root_long, allDescendents=True, type="joint", fullPath=True) or []
    return sorted([root_long] + kids, key=lambda n: n.count("|"))   # parents first


def save(path, root=DEFAULT_ROOT):
    data = {"version": 1, "root": root, "joints": []}
    for j in joints_under(root or DEFAULT_ROOT):
        parent = cmds.listRelatives(j, parent=True, fullPath=True)
        entry = {"name": _short(j), "parent": _short(parent[0]) if parent else None,
                 "rotateOrder": cmds.getAttr(j + ".rotateOrder"),
                 "radius": cmds.getAttr(j + ".radius")}
        for a in ATTRS:
            entry[a] = list(cmds.getAttr(j + "." + a)[0])
        data["joints"].append(entry)
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    _log("saved {} joints -> {}".format(len(data["joints"]), path))
    return path


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


def _set(node, attr, value):
    try:
        if isinstance(value, (list, tuple)):
            cmds.setAttr(node + "." + attr, *value)
        else:
            cmds.setAttr(node + "." + attr, value)
    except RuntimeError as e:                 # locked / connected
        cmds.warning("[KRT JointPositions] {}.{}: {}".format(_short(node), attr, e))


def load(path):
    if not os.path.isfile(path):
        raise IOError("No joint position file: {}\n(run JOINT TRANSFER / FINGER FIX, "
                      "then '...' > Save Joint Positions on this panel)".format(path))
    with open(path, "r") as f:
        data = json.load(f)
    touched, created, skipped = [], [], []
    cmds.undoInfo(openChunk=True, chunkName="KRT_LoadJointPositions")
    try:
        for e in data.get("joints", []):
            node = _one(e["name"])
            if not node:
                parent = _one(e["parent"]) if e.get("parent") else None
                if e.get("parent") and not parent:
                    skipped.append(e["name"])
                    continue
                cmds.select(clear=True)
                node = cmds.joint(name=e["name"])
                if parent:
                    node = cmds.parent(node, parent, relative=True)[0]
                node = cmds.ls(node, long=True)[0]
                created.append(e["name"])
            _set(node, "rotateOrder", e.get("rotateOrder", 0))
            for a in ATTRS:
                if a in e:
                    _set(node, a, e[a])
            if "radius" in e:
                _set(node, "radius", e["radius"])
            touched.append(node)
        # world matrices are final only now - THEN tell the skin
        for node in touched:
            _update_bind_pre_matrix(node)
    finally:
        cmds.undoInfo(closeChunk=True)
    _log("loaded {} joints from {}{}{}".format(
        len(touched), path,
        "; created: " + ", ".join(created) if created else "",
        "; skipped (parent missing): " + ", ".join(skipped) if skipped else ""))
    return len(touched)
