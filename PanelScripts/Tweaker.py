# KRT Tweaker setup script.
#
# This is the user's own Tweaker algorithm, unchanged from the version
# handed off for KRT's new Tweaker panel (request #5) - kept in its own
# file under KRT/PanelScripts/ specifically so it can be hand-edited here
# in the future without touching any of KRT's own code. KRT's Tweaker
# panel (workspace.py: _load_tweaker_module/run_tweaker_logic/
# get_tweaker_target_meshes) loads this file dynamically at runtime and
# calls create_tweaker_setup() / add_additional_tweaker_meshes() /
# system_names() directly - it does not call main() below, which is kept
# only as a reference for running this script by hand outside KRT (e.g.
# from Maya's own Script Editor), exactly as it was previously called via
# UniUtils.TweakerMain(...).

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import re, math

PLANE_SIZE, DEFAULT_CTL_SIZE = 0.01, 0.006
OTHERS, RIGGING = "others", "rigging"
COMMON_GRP, COMMON_HOLD, JNT_OFFSETS_GRP = "Tweaker_Common_Grp", "Tweaker_Hold_Jnt", "Tweaker_Jnt_Offsets_Grp"
SOURCE_ATTR = "tweakerSourceMesh"

try: del create_tweaker_setup
except: pass

try: del add_additional_tweaker_meshes
except: pass

def ln(n):
    r = cmds.ls(n, long=True) or []
    return r[0] if r else n

def same(a, b): return ln(a) == ln(b)

def mesh_shape(mesh):
    s = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, type="mesh", fullPath=True) or []
    if len(s) != 1: cmds.error("{} must contain exactly one visible mesh shape.".format(mesh))
    return s[0]

def dag_path(node):
    s = om.MSelectionList(); s.add(node)
    return s.getDagPath(0)

def dep_node(node):
    s = om.MSelectionList(); s.add(node)
    return s.getDependNode(0)

def parent_world(child, parent):
    p = cmds.listRelatives(child, parent=True, fullPath=True) or []
    if not p or not same(p[0], parent): cmds.parent(child, parent)

def ensure_group(name, parent=None, hidden=False, legacy=None):
    if not cmds.objExists(name) and legacy and cmds.objExists(legacy): name = cmds.rename(legacy, name)
    if cmds.objExists(name) and cmds.nodeType(name) != "transform": cmds.error("{} exists but is not a transform.".format(name))
    if not cmds.objExists(name): cmds.group(empty=True, name=name)
    if parent: parent_world(name, parent)
    cmds.setAttr(name + ".visibility", 0 if hidden else 1)
    return name

def clean_mesh_name(source):
    short = source.split("|")[-1]
    namespace = short.rsplit(":", 1)[0] + ":" if ":" in short else ""
    name = short.split(":")[-1]
    clean = "_".join(x for x in re.split(r"[_\-\s]+", name) if x and x.lower() not in ("geo", "cc", "base")) or "Body"
    return namespace + clean

def connected_target(source):
    for node in cmds.ls("*.{}".format(SOURCE_ATTR), objectsOnly=True, recursive=True, long=True) or []:
        c = cmds.listConnections(node + "." + SOURCE_ATTR, s=True, d=False) or []
        if c and same(c[0], source): return node
    return None

def system_names(source):
    root = clean_mesh_name(source)
    existing = connected_target(source)
    if existing:
        target = existing
        short = target.split("|")[-1]
        base = short[:-len("_tweaker_BS")] if short.endswith("_tweaker_BS") else root
    else:
        base = root; i = 2
        while cmds.objExists(base + "_tweaker_BS"):
            test = base + "_tweaker_BS"
            c = cmds.listConnections(test + "." + SOURCE_ATTR, s=True, d=False) if cmds.attributeQuery(SOURCE_ATTR, node=test, exists=True) else []
            if c and same(c[0], source): break
            base = root + "_{:02d}".format(i); i += 1
        target = base + "_tweaker_BS"
    short = target.split("|")[-1]
    return base, target, short + "Shape", base + "_Tweaker_BS_Body", base + "_Tweaker_BS_SkinCluster", base + "_Tweaker_Setups_Grp", base + "_Tweaker_ctls_Grp"

def vertex_data(vertex_name):
    if not isinstance(vertex_name, str) or ".vtx[" not in vertex_name: cmds.error('Vertex must look like "mesh.vtx[100]".')
    vertices = cmds.filterExpand(cmds.ls(vertex_name, flatten=True, long=True) or [], selectionMask=31, expand=True) or []
    if len(vertices) != 1: cmds.error('Could not find exactly one vertex from "{}".'.format(vertex_name))
    vertex, obj = vertices[0], vertices[0].split(".vtx[")[0]
    source_shape = obj if cmds.nodeType(obj) == "mesh" else mesh_shape(obj)
    source = cmds.listRelatives(source_shape, parent=True, fullPath=True)[0]
    sl = om.MSelectionList(); sl.add(vertex)
    path, component = sl.getComponent(0)
    ids = om.MFnSingleIndexedComponent(component).getElements()
    if len(ids) != 1: cmds.error("Exactly one vertex is required.")
    index = ids[0]; fn = om.MFnMesh(path)
    pos = fn.getPoint(index, om.MSpace.kWorld)
    normal = fn.getVertexNormal(index, True, om.MSpace.kWorld); normal.normalize()
    return vertex, index, source, source_shape, (pos.x, pos.y, pos.z), (normal.x, normal.y, normal.z)

def normal_matrix(pos, normal):
    y = om.MVector(*normal); y.normalize()
    ref = om.MVector(0, 0, 1) if abs(y * om.MVector(0, 0, 1)) < 0.95 else om.MVector(1, 0, 0)
    x = y ^ ref; x.normalize()
    z = x ^ y; z.normalize()
    return [x.x, x.y, x.z, 0, y.x, y.y, y.z, 0, z.x, z.y, z.z, 0, pos[0], pos[1], pos[2], 1]

def control_axis_rotation(direction):
    d = direction.lower().replace(" ", "")
    if d == "y": return (0, 0, 0)
    if d == "-y": return (180, 0, 0)
    if d == "x": return (0, 0, 90)
    if d == "-x": return (0, 0, -90)
    if d == "z": return (-90, 0, 0)
    if d == "-z": return (90, 0, 0)
    cmds.error('control_direction must be "x", "y", "z", "-x", "-y" or "-z".')

def next_index(base):
    i = 1
    suffixes = ("_setup_grp", "_plane", "_follicle", "_ctl_grp", "_ctl_offset_grp", "_ctl", "_jnt", "_jnt_offset_grp")
    while any(cmds.objExists("{}_tweaker_{:03d}{}".format(base, i, s)) for s in suffixes): i += 1
    return i

def has_influence(skin, joint):
    return any(same(x, joint) for x in (cmds.skinCluster(skin, q=True, influence=True) or []))

def bs_deforms_source(blendshape, source):
    nodes = [ln(source)] + [ln(x) for x in (cmds.listRelatives(source, shapes=True, fullPath=True) or [])]
    try: geometry = cmds.deformer(blendshape, q=True, geometry=True) or []
    except: geometry = []
    for geo in geometry:
        if not cmds.objExists(geo): continue
        if ln(geo) in nodes: return True
        if cmds.nodeType(geo) == "mesh":
            p = cmds.listRelatives(geo, parent=True, fullPath=True) or []
            if p and same(p[0], source): return True
    return False

def duplicate_without_source_skin(source, source_shape, target):
    skins = cmds.ls(cmds.listHistory(source_shape, pruneDagObjects=True) or [], type="skinCluster") or []
    states = []
    try:
        for skin in skins:
            plug = skin + ".envelope"; locked = cmds.getAttr(plug, lock=True)
            con = (cmds.listConnections(plug, s=True, d=False, p=True) or [None])[0]
            states.append((plug, cmds.getAttr(plug), locked, con))
            if locked: cmds.setAttr(plug, lock=False)
            if con: cmds.disconnectAttr(con, plug)
            cmds.setAttr(plug, 0)
        cmds.refresh(force=True)
        return cmds.duplicate(source, returnRootsOnly=True, name=target)[0]
    finally:
        for plug, value, locked, con in reversed(states):
            if not cmds.objExists(plug): continue
            try:
                if cmds.getAttr(plug, lock=True): cmds.setAttr(plug, lock=False)
                cmds.setAttr(plug, value)
                if con and cmds.objExists(con): cmds.connectAttr(con, plug, force=True)
                cmds.setAttr(plug, lock=locked)
            except Exception as error: cmds.warning("Could not restore {}: {}".format(plug, error))
        cmds.refresh(force=True)

def get_target(source, source_shape, target, target_shape):
    if cmds.objExists(target):
        if cmds.nodeType(target) != "transform": cmds.error("{} exists but is not a transform.".format(target))
        mesh_shape(target); parent_world(target, OTHERS)
        return target, False
    duplicate = duplicate_without_source_skin(source, source_shape, target)
    cmds.delete(duplicate, constructionHistory=True)
    shapes = cmds.listRelatives(duplicate, shapes=True, noIntermediate=True, type="mesh", fullPath=False) or []
    if len(shapes) != 1:
        cmds.delete(duplicate); cmds.error("Could not create a clean tweaker mesh.")
    if shapes[0] != target_shape:
        if cmds.objExists(target_shape):
            cmds.delete(duplicate); cmds.error("{} already exists.".format(target_shape))
        cmds.rename(shapes[0], target_shape)
    parent_world(duplicate, OTHERS)
    return duplicate, True

def connect_source(target, source, created):
    plug = target + "." + SOURCE_ATTR
    if not cmds.attributeQuery(SOURCE_ATTR, node=target, exists=True): cmds.addAttr(target, longName=SOURCE_ATTR, attributeType="message")
    connected = cmds.listConnections(plug, s=True, d=False) or []
    if connected:
        if not same(connected[0], source): cmds.error("{} belongs to another source mesh.".format(target))
        return
    if not created and cmds.polyEvaluate(source, vertex=True) != cmds.polyEvaluate(target, vertex=True): cmds.error("Tweaker mesh topology does not match.")
    cmds.connectAttr(source + ".message", plug, force=True)

def set_target_scale(target, value):
    values = (value, value, value) if isinstance(value, (int, float)) else value
    for axis, amount in zip("XYZ", values):
        plug = target + ".scale" + axis
        incoming = cmds.listConnections(plug, s=True, d=False, p=True) or []
        if incoming: cmds.disconnectAttr(incoming[0], plug)
        if cmds.getAttr(plug, lock=True): cmds.setAttr(plug, lock=False)
        cmds.setAttr(plug, amount)
    cmds.refresh(force=True)

def get_common_hold(common_group):
    if cmds.objExists(COMMON_HOLD):
        if cmds.nodeType(COMMON_HOLD) != "joint": cmds.error("{} exists but is not a joint.".format(COMMON_HOLD))
        parent_world(COMMON_HOLD, common_group)
        return COMMON_HOLD
    cmds.select(clear=True)
    hold = cmds.joint(name=COMMON_HOLD, position=(0, 0, 0), radius=DEFAULT_CTL_SIZE)
    parent_world(hold, common_group)
    return hold

def migrate_old_holds(skin, target, hold):
    skin_fn = oma.MFnSkinCluster(dep_node(skin))
    influences = skin_fn.influenceObjects()
    hold_path = dag_path(hold).fullPathName()
    hold_index = next((i for i, p in enumerate(influences) if p.fullPathName() == hold_path), None)
    old = [(i, p.fullPathName()) for i, p in enumerate(influences) if p.fullPathName() != hold_path and p.partialPathName().split(":")[-1].lower().endswith("tweaker_hold_jnt")]
    if hold_index is None or not old: return
    target_path = dag_path(mesh_shape(target))
    count = om.MFnMesh(target_path).numVertices
    fn = om.MFnSingleIndexedComponent(); comp = fn.create(om.MFn.kMeshVertComponent); fn.addElements(list(range(count)))
    weights, influence_count = skin_fn.getWeights(target_path, comp)
    for row in range(count):
        start = row * influence_count
        for index, _ in old:
            weights[start + hold_index] += weights[start + index]
            weights[start + index] = 0.0
    skin_fn.setWeights(target_path, comp, om.MIntArray(list(range(influence_count))), weights, False)
    for _, old_joint in old:
        try: cmds.skinCluster(skin, e=True, removeInfluence=old_joint)
        except: pass

def get_skin(target, hold, skin_name):
    skins = cmds.ls(cmds.listHistory(mesh_shape(target), pruneDagObjects=True) or [], type="skinCluster") or []
    if cmds.objExists(skin_name):
        if cmds.nodeType(skin_name) != "skinCluster" or skin_name not in skins: cmds.error("{} does not deform {}.".format(skin_name, target))
        skin = skin_name
    elif len(skins) > 1: cmds.error("{} has multiple skinClusters.".format(target))
    elif skins:
        skin = skins[0]
        if skin != skin_name:
            if cmds.objExists(skin_name): cmds.error("{} already exists.".format(skin_name))
            skin = cmds.rename(skin, skin_name)
    else:
        skin = cmds.skinCluster(hold, target, toSelectedBones=True, name=skin_name, bindMethod=0, skinMethod=0, normalizeWeights=1, maximumInfluences=8, obeyMaxInfluences=False)[0]
        cmds.skinPercent(skin, target + ".vtx[*]", transformValue=[(hold, 1)], normalize=True)
    if not has_influence(skin, hold): cmds.skinCluster(skin, e=True, addInfluence=hold, weight=0, lockWeights=False)
    migrate_old_holds(skin, target, hold)
    return skin

def bs_has_target(blendshape, target):
    target_short = target.split("|")[-1].split(":")[-1]
    aliases = cmds.aliasAttr(blendshape, q=True) or []
    return any(aliases[i].split(":")[-1] == target_short for i in range(0, len(aliases), 2))

def set_bs_weight(blendshape, target):
    target_short = target.split("|")[-1].split(":")[-1]
    aliases = cmds.aliasAttr(blendshape, q=True) or []
    for i in range(0, len(aliases), 2):
        if aliases[i].split(":")[-1] == target_short:
            cmds.setAttr(blendshape + "." + aliases[i], 1); return
    ids = cmds.getAttr(blendshape + ".weight", multiIndices=True) or []
    if ids: cmds.setAttr("{}.weight[{}]".format(blendshape, ids[-1]), 1)

def get_blendshape(target, source, source_shape, bs_name):
    # Check if a blendShape node already exists in history
    existing_bs = cmds.ls(cmds.listHistory(source_shape, pruneDagObjects=True) or [], type="blendShape") or []

    if existing_bs:
        blendshape = existing_bs[0]
        # Check if target is already added
        if not bs_has_target(blendshape, target):
            # Query next available index
            indices = cmds.getAttr(blendshape + ".weight", multiIndices=True) or []
            next_idx = max(indices) + 1 if indices else 0
            cmds.blendShape(blendshape, edit=True, target=(source, next_idx, target, 1.0))
    elif cmds.objExists(bs_name):
        blendshape = bs_name
        if not bs_has_target(blendshape, target):
            indices = cmds.getAttr(blendshape + ".weight", multiIndices=True) or []
            next_idx = max(indices) + 1 if indices else 0
            cmds.blendShape(blendshape, edit=True, target=(source, next_idx, target, 1.0))
    else:
        # Changed after=True to frontOfChain=True to avoid creating *Deformed shape node
        blendshape = cmds.blendShape(target, source, name=bs_name, origin="local", topologyCheck=False, frontOfChain=True)[0]

    set_bs_weight(blendshape, target)
    return blendshape

def source_skincluster(source_shape):
    skins = cmds.ls(cmds.listHistory(source_shape, pruneDagObjects=True) or [], type="skinCluster") or []
    return skins[0] if skins else None

def copy_vertex_skin_to_plane(source_shape, vertex_index, plane, prefix):
    source_skin = source_skincluster(source_shape)
    if not source_skin:
        cmds.warning("{} has no skinCluster. Plane skinning skipped.".format(source_shape)); return None
    src_fn = oma.MFnSkinCluster(dep_node(source_skin))
    comp_fn = om.MFnSingleIndexedComponent(); comp = comp_fn.create(om.MFn.kMeshVertComponent); comp_fn.addElement(vertex_index)
    src_weights, count = src_fn.getWeights(dag_path(source_shape), comp)
    src_influences = src_fn.influenceObjects()
    active = [(src_influences[i].fullPathName(), src_weights[i]) for i in range(count) if src_weights[i] > 0.00000001]
    if not active:
        cmds.warning("Selected vertex has no usable skin weights."); return None
    total = sum(x[1] for x in active)
    weight_map = {name: value / total for name, value in active}
    plane_skin = cmds.skinCluster([x[0] for x in active], plane, toSelectedBones=True, name=prefix + "_plane_skinCluster", bindMethod=0, skinMethod=cmds.getAttr(source_skin + ".skinningMethod"), normalizeWeights=1, maximumInfluences=max(1, len(active)), obeyMaxInfluences=False)[0]
    plane_path = dag_path(mesh_shape(plane))
    plane_fn = oma.MFnSkinCluster(dep_node(plane_skin))
    plane_influences = plane_fn.influenceObjects()
    vtx_count = om.MFnMesh(plane_path).numVertices
    plane_comp_fn = om.MFnSingleIndexedComponent(); plane_comp = plane_comp_fn.create(om.MFn.kMeshVertComponent); plane_comp_fn.addElements(list(range(vtx_count)))
    values = om.MDoubleArray()
    for _ in range(vtx_count):
        for influence in plane_influences: values.append(weight_map.get(influence.fullPathName(), 0.0))
    plane_fn.setWeights(plane_path, plane_comp, om.MIntArray(list(range(len(plane_influences)))), values, False)
    return plane_skin

def constrain_follicle_to_ctl_grp(prefix, follicle, grp):
    if not cmds.objExists(prefix + "_parentConstraint"): cmds.parentConstraint(follicle, grp, maintainOffset=False, name=prefix + "_parentConstraint")
    if not cmds.objExists(prefix + "_scaleConstraint"): cmds.scaleConstraint(follicle, grp, maintainOffset=False, name=prefix + "_scaleConstraint")

def scale_follicle_from_local(prefix, follicle, scale_source):
    if not scale_source: return
    if not cmds.objExists(scale_source): cmds.error('Scale source "{}" does not exist.'.format(scale_source))
    if not cmds.objExists(prefix + "_follicle_scaleConstraint"): cmds.scaleConstraint(scale_source, follicle, maintainOffset=True, name=prefix + "_follicle_scaleConstraint")

def connect_ctl_to_joint(ctl, joint):
    for attr in ("translate", "rotate", "scale"):
        for axis in "XYZ":
            src = ctl + "." + attr + axis
            dst = joint + "." + attr + axis
            incoming = cmds.listConnections(dst, s=True, d=False, p=True) or []
            for plug in incoming:
                try: cmds.disconnectAttr(plug, dst)
                except: pass
            if cmds.getAttr(dst, lock=True): cmds.setAttr(dst, lock=False)
            cmds.connectAttr(src, dst, force=True)

def create_tweaker(base, source_shape, vertex_index, pos, normal, setups, ctls, jnt_offsets, control_size, control_offset_y, control_direction, copy_plane_skin, follicle_scale_source):
    prefix = "{}_tweaker_{:03d}".format(base, next_index(base))
    setup = cmds.group(empty=True, name=prefix + "_setup_grp", parent=setups)

    plane = cmds.polyPlane(name=prefix + "_plane", width=PLANE_SIZE, height=PLANE_SIZE, subdivisionsX=1, subdivisionsY=1, axis=(0, 1, 0), constructionHistory=False)[0]
    cmds.rename(cmds.listRelatives(plane, shapes=True, noIntermediate=True)[0], prefix + "_planeShape")
    cmds.xform(plane, worldSpace=True, matrix=normal_matrix(pos, normal))
    cmds.makeIdentity(plane, apply=True, translate=False, rotate=False, scale=True, normal=False)
    cmds.parent(plane, setup)
    if copy_plane_skin: copy_vertex_skin_to_plane(source_shape, vertex_index, plane, prefix)

    plane_shape = mesh_shape(plane)
    follicle_shape = cmds.createNode("follicle", name=prefix + "_follicleShape")
    follicle = cmds.rename(cmds.listRelatives(follicle_shape, parent=True)[0], prefix + "_follicle")
    follicle_shape = cmds.listRelatives(follicle, shapes=True)[0]
    if follicle_shape != prefix + "_follicleShape": follicle_shape = cmds.rename(follicle_shape, prefix + "_follicleShape")
    cmds.parent(follicle, setup)
    cmds.connectAttr(plane_shape + ".outMesh", follicle_shape + ".inputMesh", force=True)
    cmds.connectAttr(plane_shape + ".worldMatrix[0]", follicle_shape + ".inputWorldMatrix", force=True)
    cmds.connectAttr(follicle_shape + ".outTranslate", follicle + ".translate", force=True)
    cmds.connectAttr(follicle_shape + ".outRotate", follicle + ".rotate", force=True)
    cmds.setAttr(follicle_shape + ".parameterU", 0.5)
    cmds.setAttr(follicle_shape + ".parameterV", 0.5)
    scale_follicle_from_local(prefix, follicle, follicle_scale_source)

    grp = cmds.group(empty=True, name=prefix + "_ctl_grp", parent=ctls)
    ctl_offset = cmds.group(empty=True, name=prefix + "_ctl_offset_grp", parent=grp)
    cmds.setAttr(ctl_offset + ".translateY", control_offset_y)
    cmds.setAttr(ctl_offset + ".rotate", *control_axis_rotation(control_direction))

    circle = cmds.circle(name=prefix + "_ctl", normal=(0, 1, 0), radius=1, sections=8, degree=3, constructionHistory=True)
    ctl, make_circle = circle[0], cmds.rename(circle[1], prefix + "_ctl_makeCircle")
    ctl_shape = cmds.rename(cmds.listRelatives(ctl, shapes=True)[0], prefix + "_ctlShape")
    cmds.parent(ctl, ctl_offset, relative=True)
    cmds.setAttr(ctl + ".translate", 0, 0, 0)
    cmds.setAttr(ctl + ".rotate", 0, 0, 0)
    cmds.setAttr(ctl + ".scale", 1, 1, 1)
    cmds.addAttr(ctl, longName="controlSize", niceName="Control Size", attributeType="double", minValue=0.0001, defaultValue=control_size, keyable=True)
    cmds.addAttr(ctl, longName="controlOffsetY", niceName="Control Offset Y", attributeType="double", defaultValue=control_offset_y, keyable=True)
    cmds.connectAttr(ctl + ".controlSize", make_circle + ".radius", force=True)
    cmds.connectAttr(ctl + ".controlOffsetY", ctl_offset + ".translateY", force=True)
    cmds.setAttr(ctl_shape + ".overrideEnabled", 1)
    cmds.setAttr(ctl_shape + ".overrideColor", 17)
    cmds.setAttr(ctl_shape + ".lineWidth", 2)

    constrain_follicle_to_ctl_grp(prefix, follicle, grp)
    cmds.refresh(force=True)

    jnt_offset = cmds.group(empty=True, name=prefix + "_jnt_offset_grp", parent=jnt_offsets)
    cmds.xform(jnt_offset, worldSpace=True, matrix=cmds.xform(ctl_offset, q=True, worldSpace=True, matrix=True))
    joint = cmds.createNode("joint", name=prefix + "_jnt", parent=jnt_offset)
    cmds.setAttr(joint + ".translate", 0, 0, 0)
    cmds.setAttr(joint + ".rotate", 0, 0, 0)
    cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
    cmds.setAttr(joint + ".scale", 1, 1, 1)
    cmds.setAttr(joint + ".radius", max(control_size * 0.25, 0.0001))
    connect_ctl_to_joint(ctl, joint)
    return ctl, joint, plane, jnt_offset

def falloff_weight(t, mode, power):
    t = max(0.0, min(1.0, t)); mode = mode.lower()
    if mode == "linear": return 1.0 - t
    if mode == "center": return max(0.0, 1.0 - math.pow(t, power))
    if mode == "outer": return max(0.0, math.pow(1.0 - t, power))
    if mode == "smooth":
        smooth = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
        return max(0.0, math.pow(1.0 - smooth, power))
    cmds.error('falloff_mode must be "smooth", "center", "outer" or "linear".')

def auto_weight_api(source_shape, target, skin, joint, hold, center_index, influence_radius=0.0, full_weight_radius=0.0, falloff=1.0, falloff_mode="smooth"):
    points = om.MFnMesh(dag_path(source_shape)).getPoints(om.MSpace.kWorld)
    center = points[center_index]
    ids, desired = [], []
    if influence_radius == 0: ids, desired = [center_index], [1.0]
    else:
        r2 = influence_radius * influence_radius
        for i, p in enumerate(points):
            dx, dy, dz = p.x - center.x, p.y - center.y, p.z - center.z
            d2 = dx * dx + dy * dy + dz * dz
            if d2 > r2: continue
            d = math.sqrt(d2)
            w = 1.0 if d <= full_weight_radius or influence_radius == full_weight_radius else falloff_weight((d - full_weight_radius) / (influence_radius - full_weight_radius), falloff_mode, falloff)
            ids.append(i); desired.append(w)
    target_path = dag_path(mesh_shape(target))
    skin_fn = oma.MFnSkinCluster(dep_node(skin))
    influences = skin_fn.influenceObjects()
    joint_path, hold_path = dag_path(joint).fullPathName(), dag_path(hold).fullPathName()
    joint_index = next((i for i, p in enumerate(influences) if p.fullPathName() == joint_path), None)
    hold_index = next((i for i, p in enumerate(influences) if p.fullPathName() == hold_path), None)
    if joint_index is None: cmds.error("{} is not an influence of {}.".format(joint, skin))
    fn = om.MFnSingleIndexedComponent(); comp = fn.create(om.MFn.kMeshVertComponent); fn.addElements(ids)
    weights, influence_count = skin_fn.getWeights(target_path, comp)
    for row, new_weight in enumerate(desired):
        start = row * influence_count
        other_total = sum(weights[start + i] for i in range(influence_count) if i != joint_index)
        if other_total > 0.0000001:
            scale = (1.0 - new_weight) / other_total
            for i in range(influence_count):
                if i != joint_index: weights[start + i] *= scale
        else:
            for i in range(influence_count): weights[start + i] = 0.0
            fallback = hold_index if hold_index is not None and hold_index != joint_index else next((i for i in range(influence_count) if i != joint_index), None)
            if fallback is not None: weights[start + fallback] = 1.0 - new_weight
        weights[start + joint_index] = new_weight
    skin_fn.setWeights(target_path, comp, om.MIntArray(list(range(influence_count))), weights, False)
    return len(ids)

def create_tweaker_setup(vertex_name, bind_scale=0.01, use_bind_scale=True, influence_radius=0.0, full_weight_radius=0.0, falloff=1.0, falloff_mode="smooth", control_size=DEFAULT_CTL_SIZE, control_offset_y=0.0, control_direction="y", copy_plane_skin=True, follicle_scale_source="local_C0_ctl"):
    vertices = [vertex_name] if isinstance(vertex_name, str) else list(vertex_name)
    if not vertices: cmds.error("Provide at least one vertex.")
    if bind_scale <= 0 or control_size <= 0: cmds.error("bind_scale and control_size must be greater than zero.")
    if control_direction.lower().replace(" ", "") not in ("x", "y", "z", "-x", "-y", "-z"): cmds.error('control_direction must be "x", "y", "z", "-x", "-y" or "-z".')
    if influence_radius < 0 or full_weight_radius < 0: cmds.error("Radius values cannot be negative.")
    if influence_radius == 0 and full_weight_radius > 0: cmds.error("full_weight_radius requires influence_radius greater than zero.")
    if influence_radius > 0 and full_weight_radius > influence_radius: cmds.error("full_weight_radius cannot be larger than influence_radius.")
    if falloff <= 0: cmds.error("falloff must be greater than zero.")
    if follicle_scale_source and not cmds.objExists(follicle_scale_source): cmds.error('follicle_scale_source "{}" does not exist.'.format(follicle_scale_source))
    cmds.undoInfo(openChunk=True, chunkName="Create Tweaker Setup")
    created_ctls = []
    try:
        for root in (OTHERS, RIGGING):
            if not cmds.objExists(root) or cmds.nodeType(root) != "transform": cmds.error('Required group "{}" does not exist.'.format(root))
        common_group = ensure_group(COMMON_GRP, OTHERS, True)
        jnt_offsets = ensure_group(JNT_OFFSETS_GRP, OTHERS, False)
        hold = get_common_hold(common_group)
        for item in vertices:
            vertex, vertex_index, source, source_shape, pos, normal = vertex_data(item)
            base, target, target_shape, bs_name, skin_name, setups_name, ctls_name = system_names(source)
            setups = ensure_group(setups_name, OTHERS, True)
            ctls = ensure_group(ctls_name, RIGGING, False, base + "_Tweaker_Controls_Grp")
            target, created = get_target(source, source_shape, target, target_shape)
            connect_source(target, source, created)
            set_target_scale(target, bind_scale if use_bind_scale else cmds.getAttr(source + ".scale")[0])
            skin = get_skin(target, hold, skin_name)
            get_blendshape(target, source, source_shape, bs_name)
            ctl, joint, plane, jnt_offset = create_tweaker(base, source_shape, vertex_index, pos, normal, setups, ctls, jnt_offsets, control_size, control_offset_y, control_direction, copy_plane_skin, follicle_scale_source)
            if not has_influence(skin, joint): cmds.skinCluster(skin, e=True, addInfluence=joint, weight=0, lockWeights=False)
            affected = auto_weight_api(source_shape, target, skin, joint, hold, vertex_index, influence_radius, full_weight_radius, falloff, falloff_mode)
            created_ctls.append(ctl)
            print("Created {} from {} | Joint offset: {} | Direction: {} | Weighted vertices: {}".format(ctl, vertex, jnt_offset, control_direction, affected))
        cmds.select(created_ctls, replace=True)
        return created_ctls
    finally: cmds.undoInfo(closeChunk=True)

def add_additional_tweaker_meshes(additional_meshes, source_mesh, bind_scale=0.01, use_bind_scale=True):
    meshes = [additional_meshes] if isinstance(additional_meshes, str) else list(additional_meshes)
    if not meshes: cmds.error("Provide at least one additional mesh.")
    if bind_scale <= 0: cmds.error("bind_scale must be greater than zero.")
    if not cmds.objExists(source_mesh): cmds.error("Source mesh '{}' does not exist.".format(source_mesh))

    source_shape = mesh_shape(source_mesh)
    base, target, target_shape, bs_name, skin_name, setups_name, ctls_name = system_names(source_mesh)

    if not cmds.objExists(target):
        cmds.error("Tweaker target mesh '{}' for source '{}' does not exist. Run create_tweaker_setup first.".format(target, source_mesh))

    source_target_shape = mesh_shape(target)
    source_skins = cmds.ls(cmds.listHistory(source_target_shape, pruneDagObjects=True) or [], type="skinCluster") or []
    if not source_skins:
        cmds.error("No skinCluster found on main tweaker target mesh '{}'.".format(target))
    source_skin = source_skins[0]

    influences = cmds.skinCluster(source_skin, query=True, influence=True) or []
    if not influences:
        cmds.error("No influences found on primary skinCluster '{}'.".format(source_skin))

    cmds.undoInfo(openChunk=True, chunkName="Add Additional Tweaker Meshes")
    processed_meshes = []
    try:
        for extra in meshes:
            if not cmds.objExists(extra):
                cmds.warning("Mesh '{}' does not exist. Skipping.".format(extra))
                continue

            extra_shape = mesh_shape(extra)
            e_base, e_target, e_target_shape, e_bs_name, e_skin_name, e_setups_name, _ = system_names(extra)

            ensure_group(e_setups_name, OTHERS, True)

            e_target, created = get_target(extra, extra_shape, e_target, e_target_shape)
            connect_source(e_target, extra, created)

            set_target_scale(e_target, bind_scale if use_bind_scale else cmds.getAttr(extra + ".scale")[0])

            e_skins = cmds.ls(cmds.listHistory(mesh_shape(e_target), pruneDagObjects=True) or [], type="skinCluster") or []
            if e_skins:
                e_skin = e_skins[0]
            else:
                e_skin = cmds.skinCluster(influences, e_target, toSelectedBones=True, name=e_skin_name, bindMethod=0, skinMethod=0, normalizeWeights=1, maximumInfluences=8, obeyMaxInfluences=False)[0]

            for inf in influences:
                if not has_influence(e_skin, inf):
                    cmds.skinCluster(e_skin, edit=True, addInfluence=inf, weight=0, lockWeights=False)

            cmds.copySkinWeights(
                sourceSkin=source_skin,
                destinationSkin=e_skin,
                noMirror=True,
                surfaceAssociation="closestPoint",
                influenceAssociation="name"
            )

            # Hooks into any pre-existing blendShape node on the additional mesh if present, or creates one
            get_blendshape(e_target, extra, extra_shape, e_bs_name)
            processed_meshes.append(extra)
            print("Successfully added tweakers to additional mesh: {}".format(extra))

        return processed_meshes
    finally:
        cmds.undoInfo(closeChunk=True)


# ==========================================
# 1. RUN PRIMARY TWEAKER SETUP
# ==========================================
def main(vtx_names, ad_meshes, src_msh, bind_scale, influenceRadius, fullWeightWadius, fallOff):
    create_tweaker_setup(
        vertex_name=vtx_names,
        bind_scale=0.01,
        use_bind_scale=bind_scale,
        influence_radius=influenceRadius,
        full_weight_radius=fullWeightWadius,
        falloff=fallOff,
        falloff_mode="center",
        control_size=0.02,
        control_offset_y=0.0,
        control_direction="-z",
        copy_plane_skin=True,
        follicle_scale_source="local_C0_ctl"
    )

    # ==========================================
    # 2. ADD ADDITIONAL MESHES (RUN AFTER)
    # ==========================================
    add_additional_tweaker_meshes(
        additional_meshes=ad_meshes,
        source_mesh=src_msh,
        bind_scale=0.01,
        use_bind_scale=False
    )

"""
Reference only - this is how the pipeline previously called this script by
hand (as UniUtils.TweakerMain(...)) before the KRT Tweaker panel existed.
KRT's own Tweaker panel does not use main() - it calls create_tweaker_setup()
and add_additional_tweaker_meshes() directly with the panel's own fields,
using these same fixed values for everything the panel doesn't expose.

TweakerMain(vtx_names =["geo_ravana_cc_base_body_lod_0.vtx[1607]","geo_ravana_cc_base_body_lod_0.vtx[3961]","geo_ravana_cc_base_body_lod_0.vtx[80969]","geo_ravana_cc_base_body_lod_0.vtx[89339]","geo_ravana_cc_base_body_lod_0.vtx[18408]","geo_ravana_cc_base_body_lod_0.vtx[19381]","geo_ravana_cc_base_body_lod_0.vtx[194120]","geo_ravana_cc_base_body_lod_0.vtx[202527]","geo_ravana_cc_base_body_lod_0.vtx[81072]","geo_ravana_cc_base_body_lod_0.vtx[89440]","geo_ravana_cc_base_body_lod_0.vtx[138281]","geo_ravana_cc_base_body_lod_0.vtx[146648]","geo_ravana_cc_base_body_lod_0.vtx[158181]","geo_ravana_cc_base_body_lod_0.vtx[162710]","geo_ravana_cc_base_body_lod_0.vtx[1721]","geo_ravana_cc_base_body_lod_0.vtx[4066]","geo_ravana_cc_base_body_lod_0.vtx[18807]","geo_ravana_cc_base_body_lod_0.vtx[19780]","geo_ravana_cc_base_body_lod_0.vtx[176153]","geo_ravana_cc_base_body_lod_0.vtx[184470]"], ad_meshes = ["geo_ravana_rudra_neck_lod_0","geo_ravana_janeu_lod_0","geo_ravana_rudra_bicep_lod_0","geo_ravana_belt_lod_0","geo_ravana_cloth_lod_0","geo_ravana_body_hair_lod_0","geo_ravana_arm_hair_lod_0"],src_msh =  "geo_ravana_cc_base_body_lod_0", bind_scale = True, influenceRadius=0.08, fullWeightWadius=0.0001, fallOff=2.0)
"""
