"""FAN + STRETCHY panel logic.

  Body fan     : fan joints on arms / legs / neck / face (+ mirror L -> R)        (Fan.py)
  Hand fan     : fan joints on all fingers                                         (Fan.py)
  Stretchy     : muscle joints (trapezius, deltoid, biceps, triceps)               (stretchy.py)

Everything is built from the default data inside Fan.py / stretchy.py. If the panel's data file (JSON in the rig's
Script folder) exists, its saved values are applied on top afterwards. "Save" writes the current fan + stretchy
attributes (the same ones stretchyFanAttrExport.py prints) into that JSON.
"""
import json
import os
import re

import maya.cmds as cmds

from . import Fan as _fan
from . import stretchy as _stretchy

TARGET_MESH = "CC_Base_Body"
_NODE_TYPES = ['joint', 'multiplyDivide', 'choice', 'plusMinusAverage', 'clamp', 'condition', 'remapValue']
_FINGER_RE = re.compile(r"_(Thumb|Index|Mid|Ring|Pinky)\d")

_ARM = dict(radius=5, offset_rot=(0, 0, 52.311))
_BODY = [("CC_Base_L_Upperarm", _ARM), ("CC_Base_L2_Upperarm", _ARM), ("CC_Base_L_Forearm", {}),
         ("CC_Base_L_Hand", {}), ("CC_Base_L_Thigh", {}), ("CC_Base_L_Calf", {}), ("CC_Base_L_Foot", {}),
         ("CC_Base_NeckTwist01", {}), ("CC_Base_NeckTwist02", {}), ("CC_Base_FacialBone", {})]
_FINGERS = ["Thumb1", "Thumb2", "Thumb3", "Index1", "Index2", "Index3", "Mid1", "Mid2", "Mid3",
            "Ring1", "Ring2", "Ring3", "Pinky1", "Pinky2", "Pinky3"]

_BASE_ATTRS = ["driveMasterX_from", "driveMasterY_from", "driveMasterZ_from",
               "rotationSpeedX", "rotationSpeedY", "rotationSpeedZ"]
_SUB_ATTRS = ["drivenByAxis", "driverStart", "driverEnd",
              "baseMeshOffsetX", "baseMeshOffsetY", "baseMeshOffsetZ",
              "targetOffsetFwdX", "targetOffsetFwdY", "targetOffsetFwdZ",
              "targetOffsetBwdX", "targetOffsetBwdY", "targetOffsetBwdZ"]
_DIRS = ["_up", "_down", "_front", "_back"]


# ── Script folder (any spelling: Script / script / Scripts / scripts) ────────────────────────────
def script_dir(rig_root, create=True):
    root = (rig_root or "").replace("\\", "/")
    if not root or not os.path.isdir(root):
        return ""
    try:
        for n in os.listdir(root):
            if n.lower() in ("script", "scripts") and os.path.isdir(os.path.join(root, n)):
                return os.path.join(root, n).replace("\\", "/")
    except OSError:
        pass
    new = os.path.join(root, "Scripts").replace("\\", "/")
    if create:
        try:
            os.makedirs(new, exist_ok=True)
        except OSError:
            return ""
    return new


def default_data_path(rig_root):
    d = script_dir(rig_root)
    return os.path.join(d, "fanStretchy_v001.json").replace("\\", "/") if d else ""


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────
def _is_hand(name):
    return bool(_FINGER_RE.search(name))


def _clear(prefixes):
    nodes = set()
    for p in prefixes:
        nodes.update(cmds.ls(p + "_fan*", type=_NODE_TYPES) or [])
    for n in nodes:
        if cmds.objExists(n):
            try:
                cmds.lockNode(n, lock=False)
                cmds.delete(n)
            except Exception:
                pass


def _body_prefixes():
    out = []
    for j, _kw in _BODY:
        out.append(j)
        out.append(j.replace("_L_", "_R_").replace("_L2_", "_R2_"))
    return out


def _finger_prefixes():
    return ["CC_Base_%s_%s" % (s, f) for s in "LR" for f in _FINGERS]


def _delete_unused_finger_joints():
    """Fingers only keep the up (and front) fan joint - same list as Fan.delete_fan_joints(), but missing ones are skipped."""
    gone = []
    for s in "LR":
        for f in _FINGERS:
            base = "CC_Base_%s_%s" % (s, f)
            gone += [base + "_fan_back_jnt", base + "_fan_down_jnt"]
            if f == "Thumb1":
                gone.append(base + "_fan_front_jnt")
    for n in gone:
        if cmds.objExists(n):
            try:
                cmds.delete(n)
            except Exception:
                pass


# ── build ────────────────────────────────────────────────────────────────────────────────────────
def build_body_fan():
    _clear(_body_prefixes())
    for jnt, kw in _BODY:
        if cmds.objExists(jnt):
            _fan.create_mesh_projected_fan_joints(jnt, TARGET_MESH, **dict({"radius": 5}, **kw))
        else:
            cmds.warning("[KRT] Fan: joint not found: " + jnt)
    _fan.L_FanValue()
    _fan.fix_and_mirror_cc_fans(TARGET_MESH)
    _fan.R_FanValue()


def build_hand_fan():
    _clear(_finger_prefixes())
    for p in _finger_prefixes():
        if cmds.objExists(p):
            _fan.create_mesh_projected_fan_joints(p, TARGET_MESH, radius=5)
        else:
            cmds.warning("[KRT] Fan: finger joint not found: " + p)
    _delete_unused_finger_joints()
    _fan.set_left_fan_attributes()
    _fan.set_right_fan_attributes()


def build_stretchy():
    _stretchy.stretchy()


# ── data file ────────────────────────────────────────────────────────────────────────────────────
def _fan_values():
    out = {}
    for base in cmds.ls("*_fan_base_jnt", type="joint") or []:
        prefix = base.replace("_fan_base_jnt", "")
        for a in _BASE_ATTRS:
            plug = base + "." + a
            if cmds.objExists(plug):
                out[plug] = cmds.getAttr(plug)
        for d in _DIRS:
            j = "%s_fan%s_jnt" % (prefix, d)
            if cmds.objExists(j):
                for a in _SUB_ATTRS:
                    plug = j + "." + a
                    if cmds.objExists(plug):
                        out[plug] = cmds.getAttr(plug)
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def _stretchy_values():
    out = {}
    for jnt in cmds.ls(type="joint") or []:
        if not cmds.attributeQuery("Muscle_Settings", node=jnt, exists=True):
            continue
        for a in ("activation_dir", "driver_min", "driver_max"):
            out["%s.%s" % (jnt, a)] = cmds.getAttr("%s.%s" % (jnt, a))
        for suf in ("_defaultLoc", "_stretchLoc"):
            loc = jnt + suf
            if cmds.objExists(loc):
                for a in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
                    out["%s.%s" % (loc, a)] = round(cmds.getAttr("%s.%s" % (loc, a)), 4)
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def save(path, merge_from=None):
    """Write the current fan + stretchy attributes of the scene to `path` (JSON). Values already in `merge_from`
    (or an existing file at `path`) for parts that are not in the scene are kept."""
    data = {"version": 1, "fan": {}, "stretchy": {}}
    for src in (merge_from, path):
        if src and os.path.isfile(src):
            try:
                with open(src, "r") as f:
                    old = json.load(f)
                data["fan"].update(old.get("fan", {}))
                data["stretchy"].update(old.get("stretchy", {}))
                break
            except Exception:
                pass
    fan, stretch = _fan_values(), _stretchy_values()
    if not fan and not stretch:
        raise RuntimeError("No fan joints or stretchy joints found in the scene - build them first.")
    data["fan"].update(fan)
    data["stretchy"].update(stretch)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return len(fan), len(stretch)


def _apply(values, want):
    n = 0
    for plug, val in values.items():
        if not want(plug) or not cmds.objExists(plug):
            continue
        if cmds.listConnections(plug, source=True, destination=False):
            continue
        try:
            cmds.setAttr(plug, val)
            n += 1
        except Exception:
            pass
    return n


def apply_data(path, body, hand, stretchy):
    """Saved values on top of the freshly built defaults. -> number of attributes set."""
    if not path or not os.path.isfile(path):
        return 0
    with open(path, "r") as f:
        data = json.load(f)

    def fan_want(plug):
        return (hand and _is_hand(plug)) or (body and not _is_hand(plug))
    n = _apply(data.get("fan", {}), fan_want)
    if stretchy:
        n += _apply(data.get("stretchy", {}), lambda p: True)
    return n


def run(body, hand, stretchy, data_path=""):
    """Build the ticked parts with the default data, then apply the saved JSON (if the file exists). -> (ok, message)"""
    if not (body or hand or stretchy):
        return False, "FAN + STRETCHY: tick at least one of Body fan / Hand fan / Stretchy joints."
    if not cmds.objExists(TARGET_MESH):
        return False, "FAN + STRETCHY: mesh '%s' is not in the scene." % TARGET_MESH
    cmds.undoInfo(openChunk=True, chunkName="KRT_fan_stretchy")
    try:
        if body:
            build_body_fan()
        if hand:
            build_hand_fan()
        if stretchy:
            build_stretchy()
        n = apply_data(data_path, body, hand, stretchy)
    finally:
        cmds.undoInfo(closeChunk=True)
    if n:
        cmds.warning("[KRT] Fan + Stretchy built; %d saved values applied from %s" % (n, os.path.basename(data_path)))
    else:
        cmds.warning("[KRT] Fan + Stretchy built with the default data (no saved data file).")
    return True, ""
