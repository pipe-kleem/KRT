# -*- coding: utf-8 -*-
"""
vnProxySkin.py  --  VN ProxySkin tool for Maya (2022+ / Python 3, tuned for Maya 2026)

WORKFLOW
  1. Select faces on a SKINNED mesh  ->  [Extract Proxy]
       - duplicates the bind-pose geometry (source mesh is never touched),
       - keeps only the selected faces, deletes history,
       - retopologizes it (polyRetopo, falls back to polyReduce) to the requested face count,
       - binds the proxy to the same joints and copies the skin from the source,
       - stores on the proxy (Attribute Editor > Extra Attributes) the source mesh, skinCluster
         and the exact source vertex ids the faces came from.
  2. Skin the proxy by hand (few faces = fast, easy weights).
  3. Select proxy mesh(es) -> [Apply Proxy Skin To Source]
       - transfers the proxy's weights back onto ONLY the stored source vertices.
       - every other vertex of the source mesh is left untouched.
       - the whole operation is one undo step (Ctrl+Z / Ctrl+Y work).

INSTALL / RUN
    import vnProxySkin
    vnProxySkin.show()
"""
import contextlib
import re

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2

WIN = "vnProxySkinWin"

ATTR_SRC_MESH = "proxySourceMesh"
ATTR_SRC_UUID = "proxySourceUUID"
ATTR_SRC_SKIN = "proxySourceSkin"
ATTR_SRC_VERTS = "proxySourceVertices"
ATTR_SRC_VCOUNT = "proxySourceVertexCount"



# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------
def _ranges(ids):
    """[0,1,2,5,7,8] -> [(0,2),(5,5),(7,8)]"""
    ids = sorted(set(int(i) for i in ids))
    out = []
    start = prev = None
    for i in ids:
        if start is None:
            start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            out.append((start, prev))
            start = prev = i
    if start is not None:
        out.append((start, prev))
    return out


def _compress(ids):
    return ",".join(str(a) if a == b else "%d:%d" % (a, b) for a, b in _ranges(ids))


def _expand(text):
    ids = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            a, b = part.split(":")
            ids.extend(range(int(a), int(b) + 1))
        else:
            ids.append(int(part))
    return ids


def _dag(path):
    sel = om2.MSelectionList()
    sel.add(path)
    return sel.getDagPath(0)


def _skin_fn(skin):
    sel = om2.MSelectionList()
    sel.add(skin)
    return oma2.MFnSkinCluster(sel.getDependNode(0))


def _vert_comp(ids):
    fn = om2.MFnSingleIndexedComponent()
    comp = fn.create(om2.MFn.kMeshVertComponent)
    fn.addElements(list(ids))
    return comp, list(fn.getElements())


def _shape_of(transform):
    shapes = cmds.listRelatives(transform, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
    return shapes[0] if shapes else None


def _parent_of(shape):
    return cmds.listRelatives(shape, parent=True, fullPath=True)[0]


def _skins_in_history(shape):
    hist = cmds.listHistory(shape, pruneDagObjects=True) or []
    return cmds.ls(hist, type="skinCluster") or []


def _long(name):
    r = cmds.ls(name, long=True)
    return r[0] if r else name


def _influences(skin):
    return [_long(j) for j in (cmds.skinCluster(skin, q=True, influence=True) or [])]


def _by_uuid(uuid):
    r = cmds.ls(uuid, long=True) if uuid else []
    return r[0] if r else None


@contextlib.contextmanager
def _envelope_off(skins):
    """Temporarily set skinCluster envelopes to 0 so geometry is in bind pose."""
    old = {}
    try:
        for s in skins:
            plug = s + ".envelope"
            try:
                old[plug] = cmds.getAttr(plug)
                cmds.setAttr(plug, 0)
            except Exception:
                pass
        yield
    finally:
        for plug, val in old.items():
            try:
                cmds.setAttr(plug, val)
            except Exception:
                pass


@contextlib.contextmanager
def _undo_chunk():
    cmds.undoInfo(openChunk=True)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


def _flags_of(cmd):
    try:
        txt = cmds.help(cmd)
        return set(re.findall(r"-([A-Za-z]+)", txt)) or None
    except Exception:
        return None


def _call(cmd, target, **kw):
    """Call a maya command passing only the flags this Maya version supports."""
    flags = _flags_of(cmd)
    if flags:
        kw = {k: v for k, v in kw.items() if k in flags}
    cmds.select(target, replace=True)
    return getattr(cmds, cmd)(target, **kw)


def _add_str_attr(node, name, nice, value):
    if not cmds.attributeQuery(name, node=node, exists=True):
        cmds.addAttr(node, longName=name, niceName=nice, dataType="string")
    cmds.setAttr("%s.%s" % (node, name), value, type="string")


# ----------------------------------------------------------------------------
# selection
# ----------------------------------------------------------------------------
def _selected_faces():
    """{shape_long_path: set(face ids)} for the active face selection."""
    sl = om2.MGlobal.getActiveSelectionList()
    data = {}
    for i in range(sl.length()):
        dag, comp = sl.getComponent(i)
        if comp.isNull() or comp.apiType() != om2.MFn.kMeshPolygonComponent:
            continue
        if dag.apiType() != om2.MFn.kMesh:
            dag.extendToShape()
        ids = om2.MFnSingleIndexedComponent(comp).getElements()
        data.setdefault(dag.fullPathName(), set()).update(ids)
    return data


def _verts_of_faces(shape, face_ids):
    dag = _dag(shape)
    fn = om2.MFnSingleIndexedComponent()
    comp = fn.create(om2.MFn.kMeshPolygonComponent)
    fn.addElements(sorted(face_ids))
    it = om2.MItMeshPolygon(dag, comp)
    verts = set()
    while not it.isDone():
        verts.update(it.getVertices())
        it.next()
    return verts


# ----------------------------------------------------------------------------
# duplicate / clean
# ----------------------------------------------------------------------------
def _clean_duplicate(dup):
    """Remove child transforms and intermediate shapes copied by duplicate."""
    for c in cmds.listRelatives(dup, children=True, fullPath=True, type="transform") or []:
        cmds.delete(c)
    for s in cmds.listRelatives(dup, shapes=True, fullPath=True) or []:
        try:
            if cmds.getAttr(s + ".intermediateObject"):
                cmds.delete(s)
        except Exception:
            pass
    if cmds.listRelatives(dup, parent=True):
        dup = cmds.parent(dup, world=True)[0]   # out of the rig hierarchy, world transform preserved
    return _long(dup)


def _bind_pose_duplicate(xform, shape, name):
    with _envelope_off(_skins_in_history(shape)):
        dup = cmds.duplicate(xform, name=name, renameChildren=True)[0]
    return _clean_duplicate(dup)


# ----------------------------------------------------------------------------
# retopo
# ----------------------------------------------------------------------------
def _reduce_mesh(proxy, opts):
    uuid = cmds.ls(proxy, uuid=True)[0]
    nf = cmds.polyEvaluate(proxy, face=True)

    if opts["mode"] == "percent":
        target = int(round(nf * (1.0 - opts["percent"] / 100.0)))
    else:
        target = int(opts["target"])
    target = max(4, target)
    if target >= nf:
        cmds.warning("Proxy has %d faces, target %d - nothing to reduce." % (nf, target))
        return proxy, nf, nf

    done = False
    if opts["retopo"]:
        try:
            _call("polyRetopo", proxy,
                  targetFaceCount=target,
                  topologyRegularity=opts["regularity"],
                  faceUniformity=opts["uniformity"],
                  anisotropy=opts["anisotropy"],
                  preserveHardEdges=opts["hard_edges"],
                  preprocessMesh=True,
                  keepOriginal=False)
            done = True
        except Exception as e:
            cmds.warning("polyRetopo failed (%s) - falling back to polyReduce." % e)

    if not done:
        pct = 100.0 * (1.0 - float(target) / nf)
        _call("polyReduce", proxy, version=1, percentage=pct, keepQuadsWeight=1.0)

    proxy = _by_uuid(uuid) or proxy
    cmds.delete(proxy, constructionHistory=True)
    return proxy, nf, cmds.polyEvaluate(proxy, face=True)


# ----------------------------------------------------------------------------
# UVs
# ----------------------------------------------------------------------------
def _transfer_uvs(src_shape, proxy):
    """Maya Transfer Attributes (UVs only, world space, closest on surface) source -> proxy."""
    pshape = _shape_of(proxy)
    src_sets = cmds.polyUVSet(src_shape, q=True, allUVSets=True) or []
    if not src_sets:
        return
    cur = (cmds.polyUVSet(src_shape, q=True, currentUVSet=True) or [src_sets[0]])[0]
    have = cmds.polyUVSet(pshape, q=True, allUVSets=True) or []
    for name in src_sets:
        if name not in have:
            cmds.polyUVSet(pshape, create=True, uvSet=name)
    cmds.transferAttributes(src_shape, pshape,
                            transferPositions=0, transferNormals=0, transferColors=0,
                            transferUVs=2, sampleSpace=0, searchMethod=3,
                            flipUVs=0, colorBorders=1)
    try:
        cmds.polyUVSet(pshape, currentUVSet=True, uvSet=cur)
    except Exception:
        pass
    cmds.delete(proxy, constructionHistory=True)   # bake: proxy stays history-free


# ----------------------------------------------------------------------------
# skin
# ----------------------------------------------------------------------------
def _infl_index_map(skin):
    """{joint_long_path: logical index in skinCluster.matrix[]}"""
    out = {}
    for i in cmds.getAttr(skin + ".matrix", multiIndices=True) or []:
        con = cmds.listConnections("%s.matrix[%d]" % (skin, i), source=True, destination=False) or []
        if con:
            out[_long(con[0])] = i
    return out


def _bind_like(src_skin, geo, name):
    infl = _influences(src_skin)
    kw = {}
    for flag in ("bindMethod", "skinMethod", "maximumInfluences", "normalizeWeights"):
        try:
            val = cmds.skinCluster(src_skin, q=True, **{flag: True})
        except Exception:
            val = None
        if val is not None:
            kw[flag] = val
    kw["dropoffRate"] = 5.0   # per-influence flag, cannot be queried without an influence name
    return cmds.skinCluster(infl + [geo], toSelectedBones=True, obeyMaxInfluences=False, name=name, **kw)[0]


def _copy_bind_matrices(src_skin, dst_skin):
    """Make dst deform like src when the rig is NOT in bind pose."""
    smap = _infl_index_map(src_skin)
    dmap = _infl_index_map(dst_skin)
    for joint, di in dmap.items():
        si = smap.get(joint)
        if si is None:
            continue
        plug = "%s.bindPreMatrix[%d]" % (dst_skin, di)
        try:
            if not cmds.listConnections(plug, source=True, destination=False):
                cmds.setAttr(plug, cmds.getAttr("%s.bindPreMatrix[%d]" % (src_skin, si)), type="matrix")
        except Exception:
            pass
    try:
        cmds.setAttr(dst_skin + ".geomMatrix", cmds.getAttr(src_skin + ".geomMatrix"), type="matrix")
    except Exception:
        pass


def _copy_weights(src_skin, dst_skin):
    src_geo = (cmds.skinCluster(src_skin, q=True, geometry=True) or [None])[0]
    dst_geo = (cmds.skinCluster(dst_skin, q=True, geometry=True) or [None])[0]
    if src_geo and dst_geo:
        cmds.select(src_geo, dst_geo, replace=True)
        cmds.refresh()
    cmds.copySkinWeights(sourceSkin=src_skin, destinationSkin=dst_skin,
                         surfaceAssociation="closestPoint",
                         influenceAssociation="closestJoint",
                         noMirror=True, normalize=True)


# ----------------------------------------------------------------------------
# STEP 1: extract proxy
# ----------------------------------------------------------------------------
def extract_proxy(shape, face_ids, opts):
    xform = _parent_of(shape)
    skins = _skins_in_history(shape)
    if not skins:
        raise RuntimeError("%s has no skinCluster." % xform)
    ssc = skins[0]

    n_verts = cmds.polyEvaluate(shape, vertex=True)
    n_faces = cmds.polyEvaluate(shape, face=True)
    src_verts = _verts_of_faces(shape, face_ids)
    src_uuid = cmds.ls(xform, uuid=True)[0]
    base = xform.split("|")[-1]

    # 1) duplicate bind-pose geometry, no history, source untouched
    proxy = _bind_pose_duplicate(xform, shape, base + "_proxy")
    pshape = _shape_of(proxy)

    # 2) keep only the selected faces
    keep = set(face_ids)
    drop = [i for i in range(n_faces) if i not in keep]
    if drop:
        cmds.delete(["%s.f[%d:%d]" % (pshape, a, b) for a, b in _ranges(drop)])
    cmds.delete(proxy, constructionHistory=True)

    # 3) retopologize / reduce
    proxy, f_before, f_after = _reduce_mesh(proxy, opts)

    # 3b) UVs (retopology discards them) - match the source
    if opts.get("transfer_uv", True):
        try:
            with _envelope_off(skins):
                _transfer_uvs(shape, proxy)
        except Exception as e:
            cmds.warning("UV transfer failed: %s" % e)

    # 4) info attributes (text fields in the Attribute Editor)
    _add_str_attr(proxy, ATTR_SRC_MESH, "Source Mesh", xform)
    _add_str_attr(proxy, ATTR_SRC_UUID, "Source UUID", src_uuid)
    _add_str_attr(proxy, ATTR_SRC_SKIN, "Source SkinCluster", ssc)
    _add_str_attr(proxy, ATTR_SRC_VERTS, "Source Vertices", _compress(src_verts))
    _add_str_attr(proxy, ATTR_SRC_VCOUNT, "Source Vertex Count", str(n_verts))

    # 5) skin
    if opts["copy_skin"]:
        psc = _bind_like(ssc, proxy, base + "_proxy_skinCluster")
        _copy_bind_matrices(ssc, psc)
        with _envelope_off(skins + [psc]):
            _copy_weights(ssc, psc)

    print("[VN ProxySkin] %s: %d faces -> %d faces, %d source verts recorded."
          % (proxy, f_before, f_after, len(src_verts)))
    return proxy


def extract_selected(opts):
    data = _selected_faces()
    if not data:
        raise RuntimeError("Select faces on a skinned mesh first.")
    proxies = []
    with _undo_chunk():
        for shape, ids in data.items():
            proxies.append(extract_proxy(shape, ids, opts))
        cmds.select(proxies, replace=True)
    return proxies


# ----------------------------------------------------------------------------
# STEP 5: apply proxy skin back to the stored vertices only
# ----------------------------------------------------------------------------
def apply_proxy(proxy):
    for a in (ATTR_SRC_VERTS, ATTR_SRC_MESH):
        if not cmds.attributeQuery(a, node=proxy, exists=True):
            raise RuntimeError("%s is not a VN ProxySkin proxy mesh (missing %s)." % (proxy, a))

    src = _by_uuid(cmds.getAttr("%s.%s" % (proxy, ATTR_SRC_UUID))) if \
        cmds.attributeQuery(ATTR_SRC_UUID, node=proxy, exists=True) else None
    src = src or _long(cmds.getAttr("%s.%s" % (proxy, ATTR_SRC_MESH)))
    if not cmds.objExists(src):
        raise RuntimeError("Source mesh for %s not found." % proxy)
    sshape = _shape_of(src)
    skins = _skins_in_history(sshape)
    if not skins:
        raise RuntimeError("%s has no skinCluster." % src)
    ssc = skins[0]

    ids = _expand(cmds.getAttr("%s.%s" % (proxy, ATTR_SRC_VERTS)))
    n_verts = cmds.polyEvaluate(sshape, vertex=True)
    if cmds.attributeQuery(ATTR_SRC_VCOUNT, node=proxy, exists=True):
        if int(cmds.getAttr("%s.%s" % (proxy, ATTR_SRC_VCOUNT))) != n_verts:
            raise RuntimeError("Source vertex count changed (%d now) - vertex ids no longer valid." % n_verts)
    if not ids or max(ids) >= n_verts:
        raise RuntimeError("Stored vertex ids are invalid for %s." % src)

    pshape = _shape_of(proxy)
    pskins = _skins_in_history(pshape)
    if not pskins:
        raise RuntimeError("%s has no skinCluster." % proxy)
    psc = pskins[0]

    # make sure the source skin knows every joint the proxy uses (weight 0 = harmless)
    s_infl = set(_influences(ssc))
    for j in _influences(psc):
        if j not in s_infl:
            cmds.skinCluster(ssc, edit=True, addInfluence=j, weight=0.0)
            cmds.warning("Added missing influence %s to %s (weight 0)." % (j, ssc))

    # temporary bind-pose twin of the source, skinned with the same joints
    tmp = _bind_pose_duplicate(src, sshape, "easyProxyTmp")
    tshape = _shape_of(tmp)
    try:
        cmds.delete(tmp, constructionHistory=True)
        tsc = _bind_like(ssc, tmp, "easyProxyTmp_skin")
        with _envelope_off([psc, tsc]):
            _copy_weights(psc, tsc)
        _transfer_subset(tsc, tshape, ssc, sshape, ids)
    finally:
        if cmds.objExists(tmp):
            cmds.delete(tmp)
    print("[VN ProxySkin] %s -> %s: wrote weights on %d vertices only." % (proxy, src, len(ids)))


def _transfer_subset(tsc, tshape, ssc, sshape, ids):
    """Copy weights tmp->source for `ids` only. Reads via API, writes via setAttr (undoable)."""
    tfn, sfn = _skin_fn(tsc), _skin_fn(ssc)
    tdag, sdag = _dag(tshape), _dag(sshape)
    comp, elems = _vert_comp(ids)

    t_idx = {p.fullPathName(): tfn.indexForInfluenceObject(p) for p in tfn.influenceObjects()}
    s_list = [(p.fullPathName(), sfn.indexForInfluenceObject(p)) for p in sfn.influenceObjects()]
    n, m = len(elems), len(s_list)

    new = [0.0] * (n * m)
    old = [0.0] * (n * m)
    for pos, (path, sidx) in enumerate(s_list):
        col_old = sfn.getWeights(sdag, comp, sidx)
        ti = t_idx.get(path)
        col_new = tfn.getWeights(tdag, comp, ti) if ti is not None else None
        for k in range(n):
            old[k * m + pos] = col_old[k]
            if col_new is not None:
                new[k * m + pos] = col_new[k]

    cmds.refresh(suspend=True)
    try:
        for k, v in enumerate(elems):
            base = k * m
            for pos, (_path, sidx) in enumerate(s_list):
                val = new[base + pos]
                if abs(val - old[base + pos]) > 1e-6:
                    cmds.setAttr("%s.weightList[%d].weights[%d]" % (ssc, v, sidx), val)
    finally:
        cmds.refresh(suspend=False)


def _is_proxy(node):
    return cmds.attributeQuery(ATTR_SRC_VERTS, node=node, exists=True)


def find_proxies(selected_only=False):
    """Selected proxies (or their shapes); if none selected, every proxy in the scene."""
    out = []
    for n in cmds.ls(selection=True, long=True, objectsOnly=True) or []:
        if cmds.nodeType(n) == "mesh":
            n = _parent_of(n)
        if cmds.nodeType(n) == "transform" and _is_proxy(n) and n not in out:
            out.append(n)
    if out or selected_only:
        return out
    return [t for t in (cmds.ls(type="transform", long=True) or []) if _is_proxy(t)]


def proxy_info(proxy):
    src = _by_uuid(cmds.getAttr("%s.%s" % (proxy, ATTR_SRC_UUID))) if \
        cmds.attributeQuery(ATTR_SRC_UUID, node=proxy, exists=True) else None
    src = src or cmds.getAttr("%s.%s" % (proxy, ATTR_SRC_MESH))
    nv = len(_expand(cmds.getAttr("%s.%s" % (proxy, ATTR_SRC_VERTS))))
    return src.split("|")[-1], nv, cmds.objExists(src)


def _resolve_source(proxy):
    src = None
    if cmds.attributeQuery(ATTR_SRC_UUID, node=proxy, exists=True):
        src = _by_uuid(cmds.getAttr("%s.%s" % (proxy, ATTR_SRC_UUID)))
    if not src and cmds.attributeQuery(ATTR_SRC_MESH, node=proxy, exists=True):
        name = cmds.getAttr("%s.%s" % (proxy, ATTR_SRC_MESH))
        src = _long(name) if cmds.objExists(name) else None
    return src


def _chain_depth(proxy):
    """How many proxy-of-proxy hops sit between this proxy and a real mesh."""
    depth, cur = 0, proxy
    for _ in range(32):
        src = _resolve_source(cur)
        if not src or not _is_proxy(src):
            break
        depth += 1
        cur = src
    return depth


def apply_selected():
    proxies = find_proxies()
    if not proxies:
        raise RuntimeError("No proxy meshes found in the scene.")
    # proxy-of-proxy: deepest first, so each level lands on its parent before the parent is applied
    proxies.sort(key=_chain_depth, reverse=True)
    with _undo_chunk():
        for p in proxies:
            apply_proxy(p)
        cmds.select(proxies, replace=True)
    return len(proxies)


# ----------------------------------------------------------------------------
# UI  (PySide, compact black theme)
# ----------------------------------------------------------------------------
try:
    from PySide6 import QtWidgets, QtCore
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2022-2024
    from PySide2 import QtWidgets, QtCore
    from shiboken2 import wrapInstance
import maya.OpenMayaUI as omui

_WINDOW = None

_QSS = """
QDialog { background: #1b1b1d; color: #d6d6d6; font-size: 11px; }
QLabel { color: #d6d6d6; background: transparent; }
QFrame#card { background: #27272a; border: 1px solid #3d3d42; border-radius: 6px; }
QLabel#cardTitle { color: #f0f0f0; font-size: 11px; font-weight: bold; letter-spacing: 1px; background: transparent; }
QLabel#step { color: #1b1b1d; background: #3fb8a5; border-radius: 8px; font-weight: bold; font-size: 10px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px; qproperty-alignment: AlignCenter; }
QLabel#hint { color: #8c8c94; font-size: 10px; }
QLabel#info { color: #cfcfd6; background: #1b1b1d; border: 1px solid #3d3d42; border-radius: 4px; padding: 5px 7px; font-size: 10px; }
QLabel#status { color: #8c8c94; font-size: 10px; background: transparent; }
QLabel#status[err="true"] { color: #ff6b6b; }
QLabel#status[ok="true"] { color: #5fd38d; }
QFrame#sep { background: #3d3d42; min-height: 1px; max-height: 1px; border: none; }
QFrame#adv { background: #1f1f22; border: 1px solid #3d3d42; border-radius: 4px; }
QComboBox, QSpinBox, QDoubleSpinBox { background: #1b1b1d; border: 1px solid #54545b; border-radius: 4px;
    padding: 2px 8px; min-height: 22px; color: #f0f0f0; selection-background-color: #3fb8a5; }
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: #8a8a94; }
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #3fb8a5; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #1b1b1d; border: 1px solid #54545b; selection-background-color: #3fb8a5; selection-color: #0b0b0b; }
QSlider::groove:horizontal { height: 4px; background: #1b1b1d; border: 1px solid #54545b; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #3fb8a5; border-radius: 3px; }
QSlider::handle:horizontal { background: #f0f0f0; border: 1px solid #3fb8a5; width: 12px; height: 12px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #ffffff; border-color: #7fe0d0; }
QCheckBox { spacing: 8px; color: #d6d6d6; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #7a7a84; background: #1b1b1d; border-radius: 3px; }
QCheckBox::indicator:hover { border-color: #3fb8a5; }
QCheckBox::indicator:checked { background: #3fb8a5; border-color: #3fb8a5; }
QToolButton { background: transparent; border: none; color: #a8a8b0; font-size: 10px; padding: 2px 0; }
QToolButton:hover { color: #ffffff; }
QPushButton { background: #3a3a40; border: 1px solid #5a5a62; border-radius: 4px; min-height: 30px;
    color: #f0f0f0; font-weight: bold; letter-spacing: 1px; font-size: 11px; }
QPushButton:hover { background: #46464d; border-color: #8a8a94; }
QPushButton:pressed { background: #2c2c31; }
QPushButton#primary { background: #3fb8a5; color: #0b1412; border: 1px solid #5fd3c0; }
QPushButton#primary:hover { background: #55cdb9; }
QPushButton#primary:pressed { background: #2f9686; }
QPushButton#blue { background: #4a7ee0; color: #ffffff; border: 1px solid #7aa2f0; }
QPushButton#blue:hover { background: #5d90f0; }
QPushButton#blue:pressed { background: #3a68c4; }
"""


def _maya_main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


class ProxySkinWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(ProxySkinWindow, self).__init__(parent)
        self.setObjectName(WIN)
        self.setWindowTitle("VN ProxySkin")
        self.setWindowFlags(QtCore.Qt.Tool)
        self.setStyleSheet(_QSS)
        self.setFixedWidth(290)
        self._vals = {"percent": 70, "count": 500}
        self._mode = "percent"
        self._job = None
        self._build()
        self._job = cmds.scriptJob(event=["SelectionChanged", self._refresh_info], protected=True)
        self._refresh_info()

    # -- widgets -------------------------------------------------------
    def _card(self, step, title):
        frame = QtWidgets.QFrame()
        frame.setObjectName("card")
        lay = QtWidgets.QVBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(8)
        num = QtWidgets.QLabel(str(step))
        num.setObjectName("step")
        ttl = QtWidgets.QLabel(title.upper())
        ttl.setObjectName("cardTitle")
        head.addWidget(num)
        head.addWidget(ttl)
        head.addStretch(1)
        lay.addLayout(head)
        sep = QtWidgets.QFrame()
        sep.setObjectName("sep")
        lay.addWidget(sep)
        return frame, lay

    def _dspin(self, val):
        w = QtWidgets.QDoubleSpinBox()
        w.setRange(0.0, 1.0)
        w.setSingleStep(0.05)
        w.setDecimals(2)
        w.setValue(val)
        w.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        w.setAlignment(QtCore.Qt.AlignRight)
        return w

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ---- card 1: extract
        c1, l1 = self._card(1, "Extract Proxy")
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["Reduce by %", "Target faces"])
        self.value = QtWidgets.QSpinBox()
        self.value.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.value.setAlignment(QtCore.Qt.AlignRight)
        row.addWidget(self.mode, 3)
        row.addWidget(self.value, 2)
        l1.addLayout(row)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        l1.addWidget(self.slider)
        self.slider.valueChanged.connect(self._slider_to_value)
        self.value.valueChanged.connect(self._value_to_slider)
        self._apply_mode("percent")
        self.mode.currentIndexChanged.connect(self._on_mode)

        self.retopo = QtWidgets.QCheckBox("Retopologize  (off = polyReduce)")
        self.retopo.setChecked(True)
        self.copyskin = QtWidgets.QCheckBox("Copy skin to proxy")
        self.copyskin.setChecked(True)
        self.transfer_uv = QtWidgets.QCheckBox("Transfer UVs from source")
        self.transfer_uv.setChecked(True)
        l1.addWidget(self.retopo)
        l1.addWidget(self.copyskin)
        l1.addWidget(self.transfer_uv)

        self.adv_btn = QtWidgets.QToolButton()
        self.adv_btn.setText("\u25B8  Retopo settings")
        self.adv_btn.setCheckable(True)
        self.adv_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.adv_btn.toggled.connect(self._toggle_adv)
        l1.addWidget(self.adv_btn)

        self.adv = QtWidgets.QFrame()
        self.adv.setObjectName("adv")
        g = QtWidgets.QGridLayout(self.adv)
        g.setContentsMargins(10, 8, 10, 8)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        self.regularity = self._dspin(0.5)
        self.uniformity = self._dspin(0.0)
        self.anisotropy = self._dspin(0.75)
        self.hard = QtWidgets.QCheckBox("Preserve hard edges")
        for i, (name, w) in enumerate((("Regularity", self.regularity),
                                       ("Uniformity", self.uniformity),
                                       ("Anisotropy", self.anisotropy))):
            g.addWidget(QtWidgets.QLabel(name), i, 0)
            g.addWidget(w, i, 1)
        g.addWidget(self.hard, 3, 0, 1, 2)
        self.adv.setVisible(False)
        l1.addWidget(self.adv)

        hint = QtWidgets.QLabel("Select faces on a skinned mesh, then extract.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        l1.addWidget(hint)
        self.btn_extract = QtWidgets.QPushButton("EXTRACT PROXY")
        self.btn_extract.setObjectName("primary")
        self.btn_extract.clicked.connect(lambda: self._run(extract_selected, self._opts()))
        l1.addWidget(self.btn_extract)
        root.addWidget(c1)

        # ---- card 2: apply
        c2, l2 = self._card(2, "Apply Skin To Source")
        self.info = QtWidgets.QLabel("")
        self.info.setObjectName("info")
        self.info.setWordWrap(True)
        l2.addWidget(self.info)
        self.btn_apply = QtWidgets.QPushButton("APPLY SKIN TO SOURCE")
        self.btn_apply.setObjectName("blue")
        self.btn_apply.clicked.connect(lambda: self._run(apply_selected))
        l2.addWidget(self.btn_apply)
        root.addWidget(c2)

        self.status = QtWidgets.QLabel("Ready.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    # -- behaviour -----------------------------------------------------
    def _refresh_info(self):
        try:
            sel = find_proxies(selected_only=True)
            if len(sel) == 1:
                name, nv, ok = proxy_info(sel[0])
                self.info.setText("Source:  %s\n%d vertices%s" % (name, nv, "" if ok else "   (MISSING!)"))
            elif len(sel) > 1:
                self.info.setText("%d proxies selected." % len(sel))
            else:
                n = len(find_proxies())
                self.info.setText("No proxy selected.\nApplies to all proxies in scene (%d)." % n)
        except Exception:
            pass

    def closeEvent(self, ev):
        if self._job is not None and cmds.scriptJob(exists=self._job):
            cmds.scriptJob(kill=self._job, force=True)
        self._job = None
        super(ProxySkinWindow, self).closeEvent(ev)

    def _apply_mode(self, mode):
        self._mode = mode
        if mode == "percent":
            self.value.setRange(1, 99)
            self.value.setSuffix(" %")
            self.slider.setRange(1, 99)
        else:
            self.value.setRange(4, 1000000)
            self.value.setSuffix(" faces")
            self.slider.setRange(4, 20000)
        self.value.setValue(self._vals[mode])
        self._value_to_slider(self.value.value())

    def _slider_to_value(self, v):
        self.value.blockSignals(True)
        self.value.setValue(v)
        self.value.blockSignals(False)

    def _value_to_slider(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)

    def _on_mode(self, idx):
        self._vals[self._mode] = self.value.value()
        self._apply_mode("percent" if idx == 0 else "count")

    def _toggle_adv(self, on):
        self.adv.setVisible(on)
        self.adv_btn.setText(("\u25BE" if on else "\u25B8") + "  Retopo settings")
        self.adjustSize()

    def _opts(self):
        v = self.value.value()
        vals = dict(self._vals)
        vals[self._mode] = v
        return {
            "mode": self._mode,
            "percent": float(vals["percent"]),
            "target": int(vals["count"]),
            "retopo": self.retopo.isChecked(),
            "regularity": self.regularity.value(),
            "uniformity": self.uniformity.value(),
            "anisotropy": self.anisotropy.value(),
            "hard_edges": self.hard.isChecked(),
            "copy_skin": self.copyskin.isChecked(),
            "transfer_uv": self.transfer_uv.isChecked(),
        }

    def _set_status(self, text, kind=""):
        self.status.setText(text)
        self.status.setProperty("err", kind == "err")
        self.status.setProperty("ok", kind == "ok")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _run(self, fn, *args):
        self._set_status("Working...")
        QtWidgets.QApplication.processEvents()
        try:
            fn(*args)
            self._set_status("Done.  Ctrl+Z to undo.", "ok")
        except Exception as e:
            cmds.warning("VN ProxySkin: %s" % e)
            self._set_status(str(e), "err")
        self._refresh_info()


def show():
    global _WINDOW
    for w in QtWidgets.QApplication.allWidgets():
        if w.objectName() == WIN:
            w.close()
            w.deleteLater()
    _WINDOW = ProxySkinWindow(_maya_main_window())
    _WINDOW.show()
    return _WINDOW


if __name__ == "__main__":
    show()