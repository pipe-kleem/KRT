import maya.cmds as cmds

# Transform attributes that aren't keyable or shown in the Channel Box by default,
# but are still needed for an exact copy
EXTRA_ATTRS = [
    "rotateOrder", "inheritsTransform",
    "rotateAxisX", "rotateAxisY", "rotateAxisZ",
    "rotatePivotX", "rotatePivotY", "rotatePivotZ",
    "scalePivotX", "scalePivotY", "scalePivotZ",
    "rotatePivotTranslateX", "rotatePivotTranslateY", "rotatePivotTranslateZ",
    "scalePivotTranslateX", "scalePivotTranslateY", "scalePivotTranslateZ",
    "shearXY", "shearXZ", "shearYZ",
    "displayHandle", "displayLocalAxis", "displayRotatePivot", "displayScalePivot",
    "offsetParentMatrix",
]


def _q(node, attr, **kw):
    return cmds.attributeQuery(attr, node=node, **kw)


def _create_attr(src, dst, attr):
    """Recreate a user-defined attribute from src on dst with the same settings."""
    plug = "{}.{}".format(src, attr)
    kw = {"longName": attr, "niceName": _q(src, attr, niceName=True)}

    short = _q(src, attr, shortName=True)
    if short != attr and not _q(dst, short, exists=True):
        kw["shortName"] = short

    at = cmds.addAttr(plug, q=True, attributeType=True)
    if at in (None, "typed"):
        dt = cmds.addAttr(plug, q=True, dataType=True)
        kw["dataType"] = dt[0] if isinstance(dt, (list, tuple)) else dt
    else:
        kw["attributeType"] = at

    if at == "enum":
        kw["enumName"] = _q(src, attr, listEnum=True)[0]
    if at == "compound":
        kw["numberOfChildren"] = _q(src, attr, numberOfChildren=True)

    # Numeric limits and default value
    if _q(src, attr, minExists=True):
        kw["minValue"] = _q(src, attr, minimum=True)[0]
    if _q(src, attr, maxExists=True):
        kw["maxValue"] = _q(src, attr, maximum=True)[0]
    if _q(src, attr, softMinExists=True):
        kw["softMinValue"] = _q(src, attr, softMin=True)[0]
    if _q(src, attr, softMaxExists=True):
        kw["softMaxValue"] = _q(src, attr, softMax=True)[0]
    try:
        dv = cmds.addAttr(plug, q=True, defaultValue=True)
        if dv is not None and "attributeType" in kw and at not in ("compound", "message"):
            kw["defaultValue"] = dv
    except Exception:
        pass

    if _q(src, attr, multi=True):
        kw["multi"] = True
        kw["indexMatters"] = _q(src, attr, indexMatters=True)
    if _q(src, attr, usedAsColor=True):
        kw["usedAsColor"] = True

    parent = _q(src, attr, listParent=True)
    if parent:
        kw["parent"] = parent[0]

    cmds.addAttr(dst, **kw)


def _copy_plug_value(s, d, copy_connections):
    """Copy the value (or incoming connection) of one plug to another."""
    incoming = cmds.listConnections(s, source=True, destination=False, plugs=True) or []
    if incoming and copy_connections:
        cmds.connectAttr(incoming[0], d, force=True)
        return
    if cmds.listConnections(d, source=True, destination=False):
        cmds.warning("Skipped {} (it has an incoming connection)".format(d))
        return

    t = cmds.getAttr(s, type=True)
    if t in ("message", "TdataCompound"):
        return
    val = cmds.getAttr(s)
    if t == "string":
        cmds.setAttr(d, val or "", type="string")
    elif t == "matrix":
        cmds.setAttr(d, val, type="matrix")
    elif isinstance(val, list) and val and isinstance(val[0], tuple):
        cmds.setAttr(d, *val[0], type=t)          # double3, float3, etc.
    else:
        cmds.setAttr(d, val)


def transfer_attributes(src=None, dst=None, include_builtin=True, copy_connections=False):
    if not (src and dst):
        sel = cmds.ls(orderedSelection=True, type="transform")
        if len(sel) != 2:
            cmds.error("Select exactly 2 transforms: source first, then target.")
        src, dst = sel

    cmds.undoInfo(openChunk=True, chunkName="transferAttributes")
    try:
        # 1) Create any user-defined attrs that are missing (listAttr returns parents before children)
        user_attrs = cmds.listAttr(src, userDefined=True) or []
        for a in user_attrs:
            if _q(dst, a, exists=True):
                st = cmds.getAttr("{}.{}".format(src, a), type=True)
                dt = cmds.getAttr("{}.{}".format(dst, a), type=True)
                if st != dt:
                    cmds.warning("{}.{} exists but its type is {} (source is {}). Skipped.".format(dst, a, dt, st))
                continue
            _create_attr(src, dst, a)
            print("Created {}.{}".format(dst, a))

        # 2) Build the full list of attributes to copy
        attrs = []
        if include_builtin:
            attrs += cmds.listAttr(src, keyable=True) or []
            attrs += cmds.listAttr(src, channelBox=True) or []
            attrs += [a for a in EXTRA_ATTRS if _q(src, a, exists=True)]
        attrs += user_attrs
        seen = set()
        attrs = [a for a in attrs if not (a in seen or seen.add(a))]

        # 3) Unlock the target, then copy values plus keyable/channel box state
        lock_state = {}
        for a in attrs:
            s, d = "{}.{}".format(src, a), "{}.{}".format(dst, a)
            if not _q(dst, a, exists=True):
                continue
            lock_state[d] = cmds.getAttr(s, lock=True)
            try:
                cmds.setAttr(d, lock=False)
                key = cmds.getAttr(s, keyable=True)
                cmds.setAttr(d, keyable=key)
                if not key:
                    cmds.setAttr(d, channelBox=cmds.getAttr(s, channelBox=True))

                if _q(src, a, multi=True):
                    for i in cmds.getAttr(s, multiIndices=True) or []:
                        _copy_plug_value("{}[{}]".format(s, i), "{}[{}]".format(d, i), copy_connections)
                elif not _q(src, a, numberOfChildren=True):   # compound children are handled one by one
                    _copy_plug_value(s, d, copy_connections)
            except Exception as e:
                cmds.warning("Could not copy {}: {}".format(a, e))

        # 4) Apply the source's lock state last
        for d, locked in lock_state.items():
            try:
                cmds.setAttr(d, lock=locked)
            except Exception:
                pass

        print("Transferred {} attributes: {} -> {}".format(len(attrs), src, dst))
    finally:
        cmds.undoInfo(closeChunk=True)


transfer_attributes()