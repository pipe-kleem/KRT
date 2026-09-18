"""Auto-split from utils.py."""
from ._shared import *


def canonical_skincluster_name(mesh):
    """The one canonical skinCluster name KRT expects for `mesh`: its own
    short (namespace/hierarchy-stripped) name plus '_SkinCluster'. A
    skinCluster named this way never has to be located by name - it's just
    what KRT creates and what the naming-convention check looks for."""
    short = mesh.split("|")[-1]
    short = short.split(":")[-1]
    return "{}{}".format(short, SKINCLUSTER_SUFFIX)


def find_mesh_skincluster(mesh):
    """Find the skinCluster actually deforming `mesh`, via construction
    history - NOT by name. Returns None if the mesh has no skinCluster."""
    if not mesh or not cmds.objExists(mesh):
        return None
    shapes = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True) or []
    for shape in shapes:
        try:
            skins = cmds.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster") or []
        except Exception:
            skins = []
        if not skins:
            continue
        for skin in skins:
            try:
                geo = cmds.skinCluster(skin, query=True, geometry=True) or []
            except Exception:
                geo = []
            if shape in (cmds.ls(geo, long=True) or []):
                return skin
        # Fallback: didn't find an exact geometry match above (unusual
        # multi-shape setups) - the first skinCluster in this shape's own
        # history is still the best guess.
        return skins[0]
    return None


def ensure_skin_influences(mesh, joints, skin_name=None):
    """Make sure `mesh`'s skinCluster (found by history, not name) has
    every joint in `joints` as an influence, adding any missing ones at 0
    weight. If the mesh has no skinCluster yet, creates one (named
    canonically, or `skin_name` if given) bound to exactly `joints`.

    Returns the skinCluster's name, or None if nothing could be done.

    This is the fix for saved skin breaking a mesh on reapply: mgear's own
    skin.importSkin() silently DROPS the stored weight for any influence
    that isn't already on the target skinCluster (see
    setInfluenceWeights() in mgear/core/skin.py) instead of adding it -
    which leaves that vertex's weights not summing to 1.0 and visibly
    distorts the mesh. Calling this before importSkin() so every stored
    influence is already present avoids that entirely.
    """
    joints = [j for j in (joints or []) if j and cmds.objExists(j)]
    skin = find_mesh_skincluster(mesh)

    if not skin:
        if not joints:
            return None
        name = skin_name or canonical_skincluster_name(mesh)
        try:
            result = cmds.skinCluster(
                joints, mesh, toSelectedBones=True, name=name,
                bindMethod=0, skinMethod=0, normalizeWeights=1,
                maximumInfluences=max(1, min(8, len(joints))),
                obeyMaxInfluences=False)
            return result[0] if result else None
        except Exception:
            traceback.print_exc()
            return None

    current = cmds.skinCluster(skin, query=True, influence=True) or []
    current_short = set(c.split("|")[-1] for c in current)
    missing = []
    for jnt in joints:
        short = jnt.split("|")[-1]
        if short in current_short:
            continue
        missing.append(jnt)
        current_short.add(short)  # guards against dupes inside `joints` itself

    if missing:
        try:
            # One call for every missing influence, not one call PER
            # missing influence (-addInfluence/-ai is a multi-use flag -
            # cmds accepts a list here and issues it as a single command).
            # A skinCluster covering a heavy mesh reallocates its WHOLE
            # weight array on every -addInfluence edit, so adding
            # influences one at a time (as this used to) meant one full
            # reallocation - and, with undo left on, one full undo-queue
            # snapshot of that array - PER missing joint. On a file with
            # hundreds of stored influences (a full character body/face
            # rig easily has 500+) that's hundreds of full-size
            # reallocations and undo snapshots for a single import, which
            # is the kind of thing that can run a machine out of memory.
            # Batching into one call cuts that to a single reallocation/
            # undo entry for the whole missing set.
            cmds.skinCluster(skin, edit=True, addInfluence=missing, weight=0, lockWeights=False)
        except Exception:
            traceback.print_exc()
    return skin


def _load_skin_file_data(file_path):
    """Raw read of a .jSkin/.gSkin/.json skin export - json for everything
    except mgear's own pickle-based .gSkin format. Raises on failure;
    callers decide how to handle that."""
    if file_path.endswith(".gSkin"):
        with open(file_path, "rb") as fp:
            return pickle.load(fp)
    with open(file_path, "r") as fp:
        return json.load(fp)


def read_skin_file_meshes(file_path):
    """Every mesh name a saved skin file covers (that still exists in the
    scene), read from its objDDic - the same set mgear's own
    skin.importSkin() will process regardless of any Meshes-field filter
    (see ensure_skin_ready_for_import). Shared by that pre-import influence
    fix and the pre-import naming check (Stage 16) so both agree on exactly
    what an import is about to touch. Returns [] on any read failure rather
    than raising - a caller can still attempt the real import even if this
    couldn't read the file."""
    try:
        data_pack = _load_skin_file_data(file_path)
    except Exception:
        traceback.print_exc()
        return []
    meshes = []
    for obj_data in data_pack.get("objDDic", []) or []:
        mesh = obj_data.get("objName")
        if mesh and cmds.objExists(mesh) and mesh not in meshes:
            meshes.append(mesh)
    return meshes


def ensure_skin_ready_for_import(file_path, meshes=None):
    """Read a .jSkin/.gSkin export and, for every mesh it covers (or just
    the ones in `meshes` if given), make sure that mesh's CURRENT
    skinCluster already has every influence joint the file expects - see
    ensure_skin_influences(). Call this BEFORE mgear.core.skin.importSkin()
    runs. Any failure here is swallowed (printed, not raised) so the
    actual import can still be attempted even if this pre-pass couldn't
    read the file."""
    try:
        data_pack = _load_skin_file_data(file_path)
    except Exception:
        traceback.print_exc()
        return

    wanted = set(m for m in (meshes or []) if m) or None
    for obj_data in data_pack.get("objDDic", []) or []:
        mesh = obj_data.get("objName")
        if not mesh or not cmds.objExists(mesh):
            continue
        if wanted and mesh not in wanted:
            continue
        joints = list((obj_data.get("weights") or {}).keys())
        if not joints:
            continue
        try:
            ensure_skin_influences(mesh, joints)
        except Exception:
            traceback.print_exc()


def find_mismatched_skinclusters(meshes=None):
    """Meshes whose skinCluster's name doesn't match KRT's
    '<mesh>_SkinCluster' convention (canonical_skincluster_name). Returns a
    list of (mesh, current_skin_name, canonical_name) tuples.

    With `meshes` given, only THOSE specific meshes are checked (via
    find_mesh_skincluster - construction history, not name) - this is how
    the Stage 16 naming check is scoped to just the mesh(es) actually
    involved in the save/import that's about to happen, instead of the
    whole scene. Leave `meshes` as None to scan every skinCluster in the
    scene instead (the original, scene-wide behavior)."""
    mismatches = []
    if meshes is not None:
        seen = set()
        for mesh in meshes:
            if not mesh or mesh in seen or not cmds.objExists(mesh):
                continue
            seen.add(mesh)
            skin = find_mesh_skincluster(mesh)
            if not skin:
                continue
            canonical = canonical_skincluster_name(mesh)
            if skin != canonical:
                mismatches.append((mesh, skin, canonical))
        return mismatches

    seen_skins = set()
    for skin in cmds.ls(type="skinCluster") or []:
        if skin in seen_skins:
            continue
        seen_skins.add(skin)
        try:
            geo = cmds.skinCluster(skin, query=True, geometry=True) or []
        except Exception:
            geo = []
        for shape in geo:
            if not cmds.objExists(shape):
                continue
            parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
            if not parents:
                continue
            mesh = parents[0]
            canonical = canonical_skincluster_name(mesh)
            if skin != canonical:
                mismatches.append((mesh, skin, canonical))
    return mismatches


def rename_mismatched_skinclusters(mismatches):
    """Rename every (mesh, current_skin_name, canonical_name) triple from
    find_mismatched_skinclusters() to its canonical name. Returns the
    number successfully renamed."""
    renamed = 0
    for mesh, current, canonical in mismatches:
        if not cmds.objExists(current):
            continue
        if cmds.objExists(canonical) and canonical != current:
            # Extremely unlikely (two meshes sharing a short name) - don't
            # clobber an unrelated node, just skip it.
            cmds.warning("[KRT] Can't rename '{}' to '{}': a node with that "
                         "name already exists.".format(current, canonical))
            continue
        try:
            cmds.rename(current, canonical)
            renamed += 1
        except Exception:
            traceback.print_exc()
    return renamed


# ---------------------------------------------------------------------------
# Re-skin (unbind + rebind, keeping weights) - KRT SkinCluster panel
# ---------------------------------------------------------------------------
# A direct port of the studio's own "RGreSkin" MEL tool, supplied as working
# Python by the rigger. The command sequence is kept deliberately faithful -
# skinCluster -e -ubk (unbind but KEEP history, so the weights survive),
# clear the stale bind-pose node(s), then rebind to the same influences -
# because that exact sequence is what the studio relies on and none of it can
# be verified from outside Maya.
#
# The ONE deliberate change from the original: it deleted every node in the
# scene matching "*bindPose*", which in a scene holding more than one
# character would also wipe unrelated rigs' bind poses. This scopes the
# delete to the dagPose nodes actually connected to the influences being
# rebound, which is the same set in a single-character scene and strictly
# safer in any other.

def _bind_poses_for_joints(joints):
    """dagPose (bindPose) nodes connected to any of these influences."""
    poses = set()
    for jnt in joints or []:
        try:
            poses.update(cmds.listConnections(jnt, type="dagPose", source=False, destination=True) or [])
        except Exception:
            continue
    return sorted(poses)

def re_skin_meshes(meshes=None):
    """Unbind and re-bind each mesh to its own existing skinCluster
    influences, keeping the weights. Returns (count, errors)."""
    try:
        import maya.mel as mel
    except Exception:
        mel = None

    # An empty list means the same thing as None here ("nothing was given"),
    # so both fall back to the selection rather than one silently erroring.
    if not meshes:
        meshes = cmds.ls(selection=True) or []
    meshes = [m for m in meshes if m]
    if not meshes:
        return 0, ["Nothing selected/listed to re-skin - select a skinned mesh first."]

    done, errors = 0, []
    for obj in meshes:
        if not cmds.objExists(obj):
            errors.append("'{}' does not exist in the scene.".format(obj))
            continue

        skin_cluster = None
        if mel is not None:
            try:
                skin_cluster = mel.eval('findRelatedSkinCluster("{}")'.format(obj)) or None
            except Exception:
                skin_cluster = None
        if not skin_cluster:
            # Same answer, found through construction history instead of
            # mGear/Maya's MEL helper (which needs the transform name and
            # can come back empty for a shape or a namespaced node).
            skin_cluster = find_mesh_skincluster(obj)
        if not skin_cluster:
            errors.append("'{}' has no skinCluster - skipped.".format(obj))
            continue

        shapes = cmds.ls(obj, dag=True, shapes=True, noIntermediate=True) or []
        if not shapes:
            errors.append("'{}' has no shape node - skipped.".format(obj))
            continue
        shape = shapes[0]

        try:
            joints = cmds.skinCluster(skin_cluster, query=True, influence=True) or []
            if not joints:
                errors.append("'{}' skinCluster has no influences - skipped.".format(obj))
                continue

            # Unbind but keep the history, so the weights survive.
            cmds.skinCluster(shape, edit=True, unbindKeepHistory=True)

            for pose in _bind_poses_for_joints(joints):
                try:
                    cmds.delete(pose)
                except Exception:
                    pass

            cmds.skinCluster(joints, shape)
            done += 1
        except Exception as e:
            errors.append("'{}' failed to re-skin: {}".format(obj, e))
    return done, errors
