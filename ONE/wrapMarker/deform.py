"""Morph mesh B onto mesh A using the marker pairs - a smooth scattered-data deformation.

Why not a wrap deformer: a wrap interpolates from the faces of its driver, and our driver is a
coarse triangulated patch, so it shreds a dense mesh. This instead fits a thin-plate spline
(biharmonic RBF) through the marker pairs: one smooth displacement field over the whole body,
exact at every marker, with no creases between driver faces and nothing evaluating per frame.
The result is baked into a blendshape, so the Offset slider just scales a stored shape.

    f(x) = SUM_i w_i * |x - P_i|  +  a0 + a1x + a2y + a3z        (phi(r) = r is the 3D biharmonic)

fitted so that f(P_i) = Q_i - P_i for every marker pair, with a little regularisation so nearly
coincident markers cannot blow the solve up.
"""
from .state import S, cmds
from . import genmesh, ui, views

try:
    import numpy as np
except ImportError:
    np = None

import maya.api.OpenMaya as om2

MORPH = "wrapMarkerMorph"
MIN_PAIRS = 4            # the affine part of the spline needs at least four, non-coplanar
CHUNK = 20000            # vertices evaluated per batch, to keep memory flat


def find_morph():
    for n in cmds.ls(MORPH + "*", type="blendShape") or []:
        return n
    return None


def has_morph():
    return find_morph() is not None


def morph_is_stale():
    """True when a morph exists but the markers have changed since it was solved - deleting
    markers, adding them, moving them or importing a set all leave it describing the old shape."""
    if not has_morph():
        return False
    try:
        return S.get("morph_sig") != genmesh._marker_sig()
    except Exception:
        return True


def _pairs():
    """(source, destination) marker positions: where B's markers are, and where A's are."""
    A, B = S["markers"]["A"], S["markers"]["B"]
    n = min(len(A), len(B))
    src = np.array([B[i]["pos"] for i in range(n)], dtype=float)
    dst = np.array([A[i]["pos"] for i in range(n)], dtype=float)
    return src, dst


def _solve_tps(src, disp, smooth):
    """Fit the spline. Returns (weights, affine) or None if the system will not solve."""
    n = len(src)
    d = np.linalg.norm(src[:, None, :] - src[None, :, :], axis=2)    # phi(r) = r
    P = np.hstack([np.ones((n, 1)), src])
    L = np.zeros((n + 4, n + 4))
    L[:n, :n] = d + np.eye(n) * smooth
    L[:n, n:] = P
    L[n:, :n] = P.T
    rhs = np.vstack([disp, np.zeros((4, 3))])
    try:
        sol = np.linalg.solve(L, rhs)
    except np.linalg.LinAlgError:
        sol, _, _, _ = np.linalg.lstsq(L, rhs, rcond=None)           # duplicate/coplanar markers
    return sol[:n], sol[n:]


def _evaluate(points, src, w, a):
    """Displacement for each point, in batches so a dense mesh stays within memory."""
    out = np.empty_like(points)
    for i in range(0, len(points), CHUNK):
        chunk = points[i:i + CHUNK]
        r = np.linalg.norm(chunk[:, None, :] - src[None, :, :], axis=2)
        out[i:i + CHUNK] = r.dot(w) + a[0] + chunk.dot(a[1:])
    return out


def _mesh_points(shape):
    sel = om2.MSelectionList()
    sel.add(shape)
    fn = om2.MFnMesh(sel.getDagPath(0))
    pts = fn.getPoints(om2.MSpace.kWorld)
    return fn, np.array([[p.x, p.y, p.z] for p in pts], dtype=float)


def create_morph(*_):
    """Build the morph and attach it to mesh B as a blendshape driven by the Offset slider."""
    if np is None:
        cmds.warning("This needs numpy, which is not available in this Maya.")
        return
    target_node = S["mesh"].get("B")
    if not (target_node and cmds.objExists(target_node)):
        cmds.warning("Load a mesh into view B first.")
        return
    if has_morph():
        cmds.warning("Mesh B is already morphed - remove it first to rebuild.")
        return
    shapes = views._mesh_shapes(target_node)
    if not shapes:
        cmds.warning("Mesh B has no mesh shape.")
        return
    if len(shapes) > 1:
        cmds.warning("Mesh B has %d shapes; morphing the first one only." % len(shapes))

    src, dst = _pairs()
    if len(src) < MIN_PAIRS:
        cmds.warning("Place at least %d marker pairs before morphing (there are %d)."
                     % (MIN_PAIRS, len(src)))
        return

    ui.message("Solving the morph from %d marker pairs..." % len(src))
    try:
        cmds.refresh()
    except Exception:
        pass

    try:
        fn, pts = _mesh_points(shapes[0])
        # a touch of regularisation, scaled to how far apart the markers are
        spread = float(np.mean(np.linalg.norm(src - src.mean(axis=0), axis=1))) or 1.0
        fitted = _solve_tps(src, dst - src, smooth=spread * 1e-4)
        if fitted is None:
            cmds.warning("Could not solve a morph from these markers.")
            return
        w, a = fitted
        moved = pts + _evaluate(pts, src, w, a)
    except Exception as e:
        import traceback
        traceback.print_exc()
        cmds.warning("Could not work out the morph: %s" % e)
        return

    cmds.undoInfo(openChunk=True, chunkName="wrapMarkerMorphB")
    try:
        shape_copy = cmds.duplicate(target_node, name=MORPH + "Target", returnRootsOnly=True)[0]
        for a_ in ("translate", "rotate", "scale"):
            for ax in "XYZ":
                try:
                    cmds.setAttr("%s.%s%s" % (shape_copy, a_, ax), lock=False)
                except Exception:
                    pass
        copy_shape = views._mesh_shapes(shape_copy)[0]
        sel = om2.MSelectionList()
        sel.add(copy_shape)
        fn2 = om2.MFnMesh(sel.getDagPath(0))
        fn2.setPoints(om2.MPointArray([om2.MPoint(*p) for p in moved]), om2.MSpace.kWorld)

        bs = cmds.blendShape(shape_copy, target_node, name=MORPH)[0]
        cmds.delete(shape_copy)                      # the shape now lives inside the blendshape
        cmds.blendShape(bs, e=True, weight=[(0, S.get("blend", 0.0))])
        S["morph_sig"] = genmesh._marker_sig()      # so we can tell later if the markers moved on
    except Exception as e:
        import traceback
        traceback.print_exc()
        delete_morph(quiet=True)
        cmds.warning("Could not attach the morph to mesh B: %s" % e)
        return
    finally:
        cmds.undoInfo(closeChunk=True)

    ui._sync_morph_btn()
    ui.message("Mesh B morph ready - the Offset slider now takes it onto mesh A's shape.")


def set_weight(value):
    """Drive the morph from the Offset slider (silent if there is no morph)."""
    bs = find_morph()
    if not bs:
        return
    try:
        cmds.blendShape(bs, e=True, weight=[(0, float(value))])
    except Exception:
        pass


def delete_morph(quiet=False, *_):
    S["morph_sig"] = None
    gone = []
    for n in (cmds.ls(MORPH + "*", type="blendShape") or []):
        try:
            cmds.delete(n)
            gone.append(n)
        except Exception as e:
            cmds.warning("Could not delete %s: %s" % (n, e))
    for n in (cmds.ls(MORPH + "Target*", transforms=True) or []):
        try:
            cmds.delete(n)
        except Exception:
            pass
    try:
        ui._sync_morph_btn()
    except Exception:
        pass
    if gone and not quiet:
        ui.message("Morph removed - mesh B is back to its own shape.")
    return bool(gone)


def toggle_morph(*_):
    if has_morph():
        if morph_is_stale():          # markers changed: rebuild rather than just dropping it
            delete_morph(quiet=True)
            create_morph()
            return
        delete_morph()
    else:
        create_morph()


# ------------------------------------------------------------- in-between markers
MAX_NEW = 2000           # per press, so one click can never flood the scene


def _edges_from_markers():
    """Unique edges of a triangulation of the marker set, in view A's screen space
    (the same triangulation Create Mesh uses, so the in-betweens follow the same layout)."""
    import maya.OpenMaya as om1
    import maya.OpenMayaUI as omui
    from . import genmesh
    view = omui.M3dView()
    omui.M3dView.getM3dViewFromModelPanel(S["panel"]["A"], view)
    xu, yu = om1.MScriptUtil(), om1.MScriptUtil()
    xp, yp = xu.asShortPtr(), yu.asShortPtr()
    A = S["markers"]["A"]
    n = min(len(A), len(S["markers"]["B"]))
    scr = []
    for mk in A[:n]:
        p = mk["pos"]
        view.worldToView(om1.MPoint(p[0], p[1], p[2]), xp, yp)
        scr.append((float(xu.getShort(xp)), float(yu.getShort(yp))))
    edges = set()
    for tri in genmesh._delaunay(scr):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edges.add((min(a, b), max(a, b)))
    return sorted(edges)


def _inbetween_count():
    """How many in-betweens per edge the user asked for (the field next to the button)."""
    try:
        return max(1, min(10, int(cmds.intField(S["ui"]["tweenlvl"], q=True, value=True))))
    except Exception:
        return 1


def add_inbetweens(*_):
    """Add marker pairs spaced along each edge of the marker triangulation.

    Each new pair is a real point on each surface, not a floating midpoint: the B-side
    midpoint is projected onto mesh B, then the current spline predicts where it belongs on
    A and that prediction is projected onto mesh A. So every pair added is a genuine
    surface-to-surface correspondence, which is what actually sharpens the morph - the gaps
    between your markers are where a spline has to guess.
    """
    if np is None:
        cmds.warning("This needs numpy, which is not available in this Maya.")
        return
    from . import markers
    A, B = S["markers"]["A"], S["markers"]["B"]
    n = min(len(A), len(B))
    if n < MIN_PAIRS:
        cmds.warning("Place at least %d marker pairs first (there are %d)." % (MIN_PAIRS, n))
        return
    if not (S["mesh"]["A"] and S["mesh"]["B"]):
        cmds.warning("Both meshes need to be loaded.")
        return
    if len(A) != len(B):
        cmds.warning("A has %d markers and B has %d - only the first %d pairs are used."
                     % (len(A), len(B), n))

    edges = _edges_from_markers()
    if not edges:
        cmds.warning("Could not work out how the markers connect up.")
        return
    per_edge = _inbetween_count()
    fractions = [(k + 1) / float(per_edge + 1) for k in range(per_edge)]
    if len(edges) * per_edge > MAX_NEW:
        edges = edges[:max(1, MAX_NEW // per_edge)]
        cmds.warning("That would add over %d markers - doing the first %d edges only."
                     % (MAX_NEW, len(edges)))

    src, dst = _pairs()
    spread = float(np.mean(np.linalg.norm(src - src.mean(axis=0), axis=1))) or 1.0
    fitted = _solve_tps(src, dst - src, smooth=spread * 1e-4)
    if fitted is None:
        cmds.warning("Could not solve the current morph, so no in-betweens were added.")
        return
    w, a = fitted

    # how far off a surface a predicted point may land before we distrust it
    lengths = [float(np.linalg.norm(src[i] - src[j])) for i, j in edges]
    tol = (sorted(lengths)[len(lengths) // 2] or spread) * 0.75

    ui.message("Adding %d in-between%s on each of %d edges..."
               % (per_edge, "" if per_edge == 1 else "s", len(edges)))
    try:
        cmds.refresh()
    except Exception:
        pass

    added, skipped = 0, 0
    group = []
    for i, j in edges:
        for f in fractions:
            along_b = src[i] * (1.0 - f) + src[j] * f
            hit_b = markers._closest_on_mesh("B", along_b)
            if not hit_b:
                skipped += 1
                continue
            pb = np.array([hit_b[0].x, hit_b[0].y, hit_b[0].z])
            want_a = pb + _evaluate(pb[None, :], src, w, a)[0]    # where the spline sends it
            hit_a = markers._closest_on_mesh("A", want_a)
            if not hit_a:
                skipped += 1
                continue
            pa = np.array([hit_a[0].x, hit_a[0].y, hit_a[0].z])
            if float(np.linalg.norm(pa - want_a)) > tol:   # landed well off mesh A: not trustworthy
                skipped += 1
                continue
            markers._add_marker("A", hit_a[0], hit_a[1], hit_a[2], group=group)
            markers._add_marker("B", hit_b[0], hit_b[1], hit_b[2], group=group)
            added += 1

    if not added:
        cmds.warning("No in-betweens could be placed (every midpoint fell too far off a surface).")
        return
    markers._commit_group(group)        # one undo step for the whole batch
    note = "Added %d in-between pairs" % added
    if skipped:
        note += " (%d skipped as unreliable)" % skipped
    ui.message(note + " - press Update Morph to rebuild with them.")
