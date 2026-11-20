"""Markers: ray casting, the numbered overlay, marking tool, undo/redo, shortcuts."""
import importlib
import json
import math
import os
import re
import sys
import time
from .state import cmds
import maya.api.OpenMaya as om2
import maya.OpenMaya as om1
import maya.OpenMayaUI as omui
from .state import QtCore, QtGui, QtWidgets, wrapInstance
from .state import CTX, DOT_RGB, NUM_SIZE, S, _ACC_KW, _FN
from . import persist, ui, views


def get_markers():
    return {k: [dict(m) for m in v] for k, v in S["markers"].items()}



# --------------------------------------------------------------- raycasting
def _mesh_fn(shape):
    if shape not in _FN:
        sl = om2.MSelectionList()
        sl.add(shape)
        fn = om2.MFnMesh(sl.getDagPath(0))
        try:
            acc = fn.autoUniformGridParams()
        except Exception:
            acc = None
        _FN[shape] = (fn, acc)
    return _FN[shape]



def _isect(shape, src, vec, maxp):
    fn, acc = _mesh_fn(shape)
    space = om2.MSpace.kWorld
    if acc is not None:
        names = [_ACC_KW[0]] if _ACC_KW[0] else ["accelerator", "accelParams"]
        for kw in names:
            try:
                res = fn.closestIntersection(src, vec, space, maxp, False, **{kw: acc})
                _ACC_KW[0] = kw
                return res
            except TypeError:
                continue
    return fn.closestIntersection(src, vec, space, maxp, False)



def _raycast(side, origin, direction):
    src = om2.MFloatPoint(origin.x, origin.y, origin.z)
    vec = om2.MFloatVector(direction.x, direction.y, direction.z)
    best = None
    for shape in views._mesh_shapes(S["mesh"][side]):
        res = _isect(shape, src, vec, 1.0e9)
        if not res or res[2] < 0:
            continue
        if best is None or res[1] < best[0]:
            best = (res[1], res[0], res[2], shape)
    if not best:
        return None
    return best[1], best[2], best[3]



def _mirror_point(side, pos):
    """Closest point on the SAME mesh to the X-mirrored position -> (point, face, shape), or None."""
    target = om2.MPoint(-pos[0], pos[1], pos[2])
    best = None
    for shape in views._mesh_shapes(S["mesh"][side]):
        fn, _ = _mesh_fn(shape)
        try:
            pt, face = fn.getClosestPoint(target, om2.MSpace.kWorld)
        except Exception:
            continue
        d = (pt.x - target.x) ** 2 + (pt.y - target.y) ** 2 + (pt.z - target.z) ** 2
        if best is None or d < best[0]:
            best = (d, pt, face, shape)
    if best is None:
        return None
    return best[1], best[2], best[3]



def _closest_on_mesh(side, pos):
    """Closest point on the CURRENT mesh surface to pos -> (point, face, shape), or None
    (the mesh may have been deformed - moved joints, a blendshape, a subdivide - since the
    marker was placed, so this is recomputed rather than trusting the stored position)."""
    target = om2.MPoint(pos[0], pos[1], pos[2])
    best = None
    for shape in views._mesh_shapes(S["mesh"][side]):
        fn, _ = _mesh_fn(shape)
        try:
            pt, face = fn.getClosestPoint(target, om2.MSpace.kWorld)
        except Exception:
            continue
        d = (pt.x - target.x) ** 2 + (pt.y - target.y) ** 2 + (pt.z - target.z) ** 2
        if best is None or d < best[0]:
            best = (d, pt, face, shape)
    if best is None:
        return None
    return best[1], best[2], best[3]



# ------------------------------------------------- sticking markers to the surface
# A marker is bound to the three mesh vertices of the triangle it landed on, plus the
# barycentric weights inside that triangle. Its position is then DERIVED from the live
# mesh every time, so it follows any deformation exactly and - crucially - reversibly.
# (Re-snapping to the "closest point" instead made each deform/undeform cycle walk the
# marker a little further across the surface.)

def _barycentric(p, a, b, c):
    """Weights of p inside triangle abc, plus how far outside the triangle it fell."""
    v0 = b - a
    v1 = c - a
    v2 = p - a
    d00, d01, d11 = v0 * v0, v0 * v1, v1 * v1
    d20, d21 = v2 * v0, v2 * v1
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-12:
        return None
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    err = sum(max(0.0, -x) + max(0.0, x - 1.0) for x in (u, v, w))
    return (u, v, w), err


def bind_marker(side, mk, point=None, face=None, shape=None):
    """Tie a marker to the triangle it sits on. Returns True when it took."""
    shape = shape or mk.get("shape")
    pos = point if point is not None else om2.MPoint(*mk["pos"])
    if face is None:
        hit = _closest_on_mesh(side, (pos.x, pos.y, pos.z))
        if not hit:
            return False
        pos, face, shape = hit[0], hit[1], hit[2]
    try:
        fn, _ = _mesh_fn(shape)
        verts = fn.getPolygonVertices(int(face))
    except Exception:
        return False
    if len(verts) < 3:
        return False
    best = None
    for i in range(1, len(verts) - 1):            # fan-triangulate the face
        tri = (verts[0], verts[i], verts[i + 1])
        try:
            pts = [fn.getPoint(v, om2.MSpace.kWorld) for v in tri]
        except Exception:
            return False
        got = _barycentric(pos, pts[0], pts[1], pts[2])
        if got is None:
            continue
        weights, err = got
        if best is None or err < best[0]:
            best = (err, tri, weights)
    if best is None:
        return False
    mk["bind"] = {"shape": shape, "tri": [int(v) for v in best[1]],
                  "w": [float(x) for x in best[2]]}
    mk["face"] = int(face)
    mk["shape"] = shape
    return True


def bound_position(mk):
    """Where a bound marker is right now, read off the live mesh. None if it cannot be read."""
    b = mk.get("bind")
    if not b:
        return None
    try:
        fn, _ = _mesh_fn(b["shape"])
        pts = [fn.getPoint(v, om2.MSpace.kWorld) for v in b["tri"]]
    except Exception:
        return None
    w = b["w"]
    return (pts[0].x * w[0] + pts[1].x * w[1] + pts[2].x * w[2],
            pts[0].y * w[0] + pts[1].y * w[1] + pts[2].y * w[2],
            pts[0].z * w[0] + pts[1].z * w[1] + pts[2].z * w[2])


def _mesh_stamp(side):
    """Cheap fingerprint of a mesh's current shape - one query instead of a closest-point
    test per marker. If this has not changed, nothing has deformed and no marker can have
    come off the surface, so the whole snap pass can be skipped."""
    node = S["mesh"][side]
    if not node:
        return None
    try:
        return tuple(round(v, 5) for v in cmds.exactWorldBoundingBox(node))
    except Exception:
        return None


def snap_markers(side=None, force=False):
    """Put every marker where its bound triangle is now.

    This is exact and reversible: deform the mesh and the markers follow, undeform it and
    they go back to precisely where they were. Markers with no binding yet (placed before
    this existed, or imported) get bound once, by closest point, and are stable after that."""
    stamps = S.setdefault("stamp", {})
    for sd in (("A", "B") if side is None else (side,)):
        if not S["mesh"][sd] or not cmds.objExists(S["mesh"][sd]):
            continue
        if not S["markers"][sd]:
            continue
        stamp = _mesh_stamp(sd)
        moved = stamp is None or stamps.get(sd) != stamp
        # A marker that cannot be bound is remembered as such: without this, retrying it on
        # every refresh means a closest-point search per marker several times a second, for
        # ever, which is enough on its own to bring Maya to a crawl.
        todo = [mk for mk in S["markers"][sd] if not mk.get("bind") and not mk.get("nobind")]
        if not (force or moved or todo):
            continue                              # mesh unchanged, everything already bound
        stamps[sd] = stamp
        retry = force or moved                    # only worth re-trying failures if something changed
        for mk in S["markers"][sd]:
            if not mk.get("bind") and (retry or not mk.get("nobind")):
                if bind_marker(sd, mk):           # one-off for older / imported markers
                    mk.pop("nobind", None)
                else:
                    mk["nobind"] = True
                    continue
            pos = bound_position(mk)
            if pos is None and retry:             # binding went stale (topology changed?)
                if bind_marker(sd, mk):
                    pos = bound_position(mk)
                else:
                    mk["nobind"] = True
            if pos is not None:
                mk["pos"] = pos
                mk.pop("nobind", None)



def _occluded(side, pos, cam):
    d = om2.MFloatVector(pos[0] - cam[0], pos[1] - cam[1], pos[2] - cam[2])
    dist = d.length()
    if dist <= 0:
        return False
    d.normalize()
    src = om2.MFloatPoint(cam[0], cam[1], cam[2])
    tol = dist * 0.003
    for shape in views._mesh_shapes(S["mesh"][side]):
        res = _isect(shape, src, d, dist + tol)
        if res and res[2] >= 0 and res[1] < dist - tol:
            return True
    return False



# ---------------------------------------------------------- 2D dot overlay
class _Overlay(QtWidgets.QWidget):
    """Click-through transparent window that floats over a viewport and paints the
    marker numbers. It is NOT a child of the GL viewport (that blanks it)."""

    def __init__(self, target, panel, side):
        owner = target.window()
        flags = (QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
                 | QtCore.Qt.WindowTransparentForInput | QtCore.Qt.WindowDoesNotAcceptFocus)
        super(_Overlay, self).__init__(owner, flags)
        self.target, self.panel, self.side = target, panel, side
        for a in (QtCore.Qt.WA_TranslucentBackground, QtCore.Qt.WA_TransparentForMouseEvents,
                  QtCore.Qt.WA_ShowWithoutActivating, QtCore.Qt.WA_NoSystemBackground):
            self.setAttribute(a)
        self._vis, self._vis_key, self._vis_t = None, None, 0.0
        target.installEventFilter(self)
        owner.installEventFilter(self)
        self.sync()

    def eventFilter(self, obj, ev):
        if ev.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Move, QtCore.QEvent.Show,
                         QtCore.QEvent.Hide, QtCore.QEvent.WindowStateChange):
            QtCore.QTimer.singleShot(0, self.sync)
        return False

    def sync(self):
        try:
            t = self.target
            if t.isVisible() and not t.window().isMinimized():
                self.setGeometry(QtCore.QRect(t.mapToGlobal(QtCore.QPoint(0, 0)), t.size()))
                if not self.isVisible():
                    self.show()
            else:
                self.hide()
        except RuntimeError:
            pass

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        pts = S["markers"][self.side]
        self._draw_tag(p, pts)
        cam = S["cam"][self.side]
        if pts and cam and not S.get("hidden") and cmds.objExists(cam):
            self._draw_numbers(p, pts)       # hidden: no numbers, and no occlusion raycasts either
        p.end()

    def _draw_tag(self, p, pts):
        """Small title badge in the corner: side, mesh name, marker count."""
        side, mesh = self.side, S["mesh"][self.side]
        rgb = QtGui.QColor(*DOT_RGB[side])
        font = p.font()
        font.setPixelSize(12)
        font.setBold(True)
        p.setFont(font)
        if not mesh:
            p.setPen(QtGui.QColor(210, 210, 210, 110))
            big = p.font()
            big.setPixelSize(16)
            p.setFont(big)
            p.drawText(self.rect(), QtCore.Qt.AlignCenter, "Load mesh %s above" % side)
            p.setFont(font)
            txt = "%s   -   no mesh" % side
        else:
            name = mesh.split("|")[-1].split(":")[-1]
            txt = "%s   %s   |   %d markers" % (side, name, len(pts))
            if side == "A" and S["blend"] > 0:
                txt += "   |   offset %.2f" % S["blend"]
        w = QtGui.QFontMetrics(font).boundingRect(txt).width() + 30
        box = QtCore.QRectF(10, 10, w, 24)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(18, 19, 21, 215))
        p.drawRoundedRect(box, 5, 5)
        p.setBrush(rgb)
        p.drawRoundedRect(QtCore.QRectF(10, 10, 5, 24), 2, 2)
        p.setPen(QtGui.QColor(232, 234, 237))
        p.drawText(box.adjusted(16, 0, 0, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, txt)

    def _visibility(self, pts, cam, cam_mat):
        """Which numbers are in front of the mesh rather than behind it.

        The test is a raycast per marker, so doing it on every repaint meant hundreds of
        raycasts a second against a dense mesh - that alone could make Maya look hung. It is
        cached, and only redone when the camera or the mesh has actually moved, and at most a
        few times a second while orbiting."""
        key = (tuple(round(v, 4) for v in cam_mat), len(pts),
               round(S["blend"], 4), S.get("stamp", {}).get(self.side))
        now = time.time()
        if self._vis is not None and (key == self._vis_key or now - self._vis_t < 0.15):
            return self._vis
        self._vis_key, self._vis_t = key, now
        vis = {}
        for i, m in enumerate(pts, 1):
            try:
                vis[i] = not _occluded(self.side, m["pos"], cam)
            except Exception:
                vis[i] = True
        self._vis = vis
        return vis


    def _draw_numbers(self, p, pts):
        view = omui.M3dView()
        omui.M3dView.getM3dViewFromModelPanel(self.panel, view)
        pw, ph = view.portWidth(), view.portHeight()
        if pw <= 0 or ph <= 0:
            return
        sx, sy = self.width() / float(pw), self.height() / float(ph)
        cam_mat = cmds.xform(S["cam"][self.side], q=True, ws=True, matrix=True)
        cam = cam_mat[12:15]
        vis = self._visibility(pts, cam, cam_mat)
        font = p.font()
        font.setBold(True)
        font.setPixelSize(NUM_SIZE)
        p.setFont(font)
        color = QtGui.QColor(*DOT_RGB[self.side])
        shadow = QtGui.QColor(0, 0, 0)
        xu, yu = om1.MScriptUtil(), om1.MScriptUtil()
        xp, yp = xu.asShortPtr(), yu.asShortPtr()
        for i, m in enumerate(pts, 1):
            pos = m["pos"]
            moving = False
            t = S["blend"]
            if self.side == "A" and t > 0 and i <= len(S["markers"]["B"]):
                b = S["markers"]["B"][i - 1]["pos"]  # same-numbered marker on B
                pos = tuple(pos[k] + (b[k] - pos[k]) * t for k in range(3))
                moving = True
            if not view.worldToView(om1.MPoint(pos[0], pos[1], pos[2]), xp, yp):
                continue
            if not moving and not vis.get(i, True):
                continue
            x = xu.getShort(xp) * sx
            y = (ph - yu.getShort(yp)) * sy
            box = QtCore.QRectF(x - 30, y - 10, 60, 20)  # number centred on the point
            p.setPen(shadow)  # 1px dark outline so it reads on any shading
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                p.drawText(box.translated(dx, dy), QtCore.Qt.AlignCenter, str(i))
            p.setPen(color)
            p.drawText(box, QtCore.Qt.AlignCenter, str(i))



SNAP_EVERY = 0.25        # seconds; repaints fire constantly, snapping every one of them was heavy


def _update_overlays(*_):
    views._enforce_isolation()
    now = time.time()
    if now - S.get("snap_t", 0.0) > SNAP_EVERY:   # keeps markers on the surface whatever moved the mesh
        S["snap_t"] = now
        snap_markers()                            # returns at once unless a mesh actually moved
    for side in ("A", "B"):
        ov = S["overlay"][side]
        if ov is not None:
            try:
                ov.sync()
                ov.update()
            except RuntimeError:
                S["overlay"][side] = None
    if now - S.get("sb_t", 0.0) > SNAP_EVERY:     # rebuilding this string every frame is not free
        S["sb_t"] = now
        ui._update_statusbar()



def _make_overlays():
    for side in ("A", "B"):
        panel = S["panel"][side]
        if not panel or not cmds.modelPanel(panel, exists=True):
            continue
        view = omui.M3dView()
        omui.M3dView.getM3dViewFromModelPanel(panel, view)
        widget = wrapInstance(int(view.widget()), QtWidgets.QWidget)
        S["overlay"][side] = _Overlay(widget, panel, side)
        if not S["shortcuts"]:
            _make_shortcuts(widget.window())
        try:  # repaint right after each viewport render so dots track the camera
            cid = omui.MUiMessage.add3dViewPostRenderMsgCallback(panel, _update_overlays)
            S["callbacks"].append(cid)
        except Exception:
            pass



# ----------------------------------------------------------------- markers
def _add_marker(side, pt, face, shape, group=None):
    """Place one marker. Pass `group` (a list) to batch several markers (e.g. a symmetric pair)
    into a single undo step - call _commit_group(group) once afterwards yourself."""
    mk = {"pos": (pt.x, pt.y, pt.z), "face": int(face), "shape": shape}
    bind_marker(side, mk, point=om2.MPoint(pt.x, pt.y, pt.z), face=face, shape=shape)
    S["markers"][side].append(mk)
    if group is not None:
        group.append((side, mk))
        return mk
    _commit_group([(side, mk)])
    return mk



def state_of(mk):
    """Snapshot of where a marker currently sits (for undoing a move)."""
    b = mk.get("bind")
    return {"pos": tuple(mk["pos"]), "face": int(mk["face"]), "shape": mk["shape"],
            "bind": dict(b) if b else None}


def _restore(mk, st):
    mk["pos"], mk["face"], mk["shape"] = st["pos"], st["face"], st["shape"]
    if st.get("bind"):
        mk["bind"] = dict(st["bind"])
    else:
        mk.pop("bind", None)


def _commit_group(group):
    """Record one undo step covering every (side, marker) in `group` together."""
    if not group:
        return
    S["history"].append({"kind": "add", "items": list(group)})
    S["redo"] = []
    snap_markers()
    _update_overlays()
    ui._sync_action_btns()       # markers changed -> mesh / morph may need rebuilding
    persist.save_to_scene()



def _undo(*_):
    """Step back one action: a placement (pair included) is removed, a move goes back where it was."""
    if not S["history"]:
        return
    entry = S["history"].pop()
    kind = entry.get("kind")
    if kind == "move":
        for side, mk, before, after in entry["items"]:
            _restore(mk, before)
    elif kind == "delete":                       # put the deleted marker(s) back where they were
        for side, mk, at in entry["items"]:
            S["markers"][side].insert(min(at, len(S["markers"][side])), mk)
    else:
        for side, mk in entry["items"]:
            if mk in S["markers"][side]:
                S["markers"][side].remove(mk)
    S["redo"].append(entry)
    snap_markers()
    _update_overlays()
    ui._sync_action_btns()       # markers changed -> mesh / morph may need rebuilding
    persist.save_to_scene()



def _redo(*_):
    if not S["redo"]:
        return
    entry = S["redo"].pop()
    kind = entry.get("kind")
    if kind == "move":
        for side, mk, before, after in entry["items"]:
            _restore(mk, after)
    elif kind == "delete":
        for side, mk, at in sorted(entry["items"], key=lambda r: -r[2]):
            if mk in S["markers"][side]:
                S["markers"][side].remove(mk)
    else:
        for side, mk in entry["items"]:
            if mk not in S["markers"][side]:
                S["markers"][side].append(mk)
    S["history"].append(entry)
    snap_markers()
    _update_overlays()
    ui._sync_action_btns()       # markers changed -> mesh / morph may need rebuilding
    persist.save_to_scene()



def _pointer_over_viewport():
    pos = QtGui.QCursor.pos()
    for side in ("A", "B"):
        ov = S["overlay"][side]
        try:
            if ov is not None and ov.target.rect().contains(ov.target.mapFromGlobal(pos)):
                return True
        except RuntimeError:
            pass
    return False



def _focus_line_edit():
    """The text field being typed in, or None.
    A field that merely kept focus after Enter / Load doesn't count while the pointer is over
    a viewport - then the shortcut should run (and the field lets go of the focus)."""
    f = QtWidgets.QApplication.focusWidget()
    if not isinstance(f, QtWidgets.QLineEdit):
        return None
    if _pointer_over_viewport():
        f.clearFocus()
        return None
    return f



def _key_undo():
    f = _focus_line_edit()
    f.undo() if f else _undo()



def _key_redo():
    f = _focus_line_edit()
    f.redo() if f else _redo()



def _key_shift_z():
    f = _focus_line_edit()
    f.insert("Z") if f else _redo()  # typing a capital Z in a field still works



def _frame_all():
    """F: frame the mesh in the panel under the pointer (cameras are shared, so both
    views follow). Falls back to both meshes if the pointer isn't over a panel."""
    cam = S["cam"]["A"]
    panel = cmds.getPanel(underPointer=True)
    side = next((sd for sd in ("A", "B") if S["panel"][sd] == panel), None)
    nodes = [S["mesh"][side]] if side else [S["mesh"]["A"], S["mesh"]["B"]]
    meshes = [m for m in nodes if m and cmds.objExists(m)]
    if cam and cmds.objExists(cam) and meshes:
        cmds.viewFit(cam, *meshes, fitFactor=0.9)
        _update_overlays()



def _focus_point(pt):
    """Move the shared camera in on one world point (keeps the current view direction)."""
    cam = S["cam"]["A"]
    if not cam or not cmds.objExists(cam):
        return
    m = cmds.xform(cam, q=True, ws=True, matrix=True)
    fwd = om2.MVector(-m[8], -m[9], -m[10]).normal()
    shape = cmds.listRelatives(cam, shapes=True)[0]
    film = min(cmds.getAttr(shape + ".horizontalFilmAperture"),
               cmds.getAttr(shape + ".verticalFilmAperture")) * 25.4
    fov = 2.0 * math.atan(film / 2.0 / cmds.getAttr(shape + ".focalLength"))
    dist = max(S["size"] * 6.0, 1e-3) * 1.4 / math.tan(fov / 2.0)
    pos = om2.MVector(*pt) - fwd * dist
    cmds.xform(cam, ws=True, t=(pos.x, pos.y, pos.z))
    try:
        cmds.setAttr(shape + ".centerOfInterest", dist)
    except Exception:
        pass
    _update_overlays()



def _focus_recent_marker():
    """Ctrl+F: focus on the marker placed most recently (either view)."""
    if not S["history"]:
        _notify("No markers yet.")
        return
    last = S["history"][-1]["items"][-1]
    side, m = last[0], last[1]
    pos = m["pos"]
    idx = S["markers"][side].index(m) if m in S["markers"][side] else -1
    if side == "A" and S["blend"] > 0 and 0 <= idx < len(S["markers"]["B"]):
        b, t = S["markers"]["B"][idx]["pos"], S["blend"]  # follow the slid number
        pos = tuple(pos[k] + (b[k] - pos[k]) * t for k in range(3))
    _focus_point(pos)



def _key_focus_recent():
    if not _focus_line_edit():
        _focus_recent_marker()



def _key_frame():
    f = _focus_line_edit()
    f.insert("f") if f else _frame_all()



def _make_shortcuts(owner):
    QShortcut = getattr(QtGui, "QShortcut", None) or QtWidgets.QShortcut
    for seq, fn in (("Ctrl+Z", _key_undo), ("Shift+Z", _key_shift_z), ("Ctrl+Y", _key_redo),
                    ("F", _key_frame), ("Ctrl+F", _key_focus_recent)):
        sc = QShortcut(QtGui.QKeySequence(seq), owner)
        sc.setContext(QtCore.Qt.WindowShortcut)
        sc.activated.connect(fn)
        S["shortcuts"].append(sc)



def _notify(msg):
    """Show a message in the Maya command line AND in the tool's status bar."""
    cmds.warning("wrap_marker_tool: " + msg)
    sb = ui._ok("statusbar")
    if sb:
        cmds.text(sb, e=True, label="  " + msg)



def _pointer_view():
    """Which viewport is the cursor over? -> (side, panel, view-pixel x, y) or None.
    Uses the cursor position directly, so it doesn't depend on Maya's pointer query."""
    pos = QtGui.QCursor.pos()
    for side in ("A", "B"):
        ov = S["overlay"][side]
        if ov is None:
            continue
        try:
            t = ov.target
            loc = t.mapFromGlobal(pos)
            if not t.rect().contains(loc) or t.width() <= 0 or t.height() <= 0:
                continue
            view = omui.M3dView()
            omui.M3dView.getM3dViewFromModelPanel(S["panel"][side], view)
            pw, ph = view.portWidth(), view.portHeight()
            x = loc.x() * pw / float(t.width())
            y = (t.height() - loc.y()) * ph / float(t.height())
            return side, S["panel"][side], view, int(x), int(y)
        except RuntimeError:
            continue
    return None



def _project(view, pos):
    """World point -> (x, y) in view pixels (origin bottom-left), or None when behind the camera."""
    xu, yu = om1.MScriptUtil(), om1.MScriptUtil()
    xp, yp = xu.asShortPtr(), yu.asShortPtr()
    if not view.worldToView(om1.MPoint(pos[0], pos[1], pos[2]), xp, yp):
        return None
    return xu.getShort(xp), yu.getShort(yp)



def _pick_marker(side, view, x, y, radius=20):
    """Index of the visible marker nearest the cursor (within `radius` px), else None."""
    origin, direction = om1.MPoint(), om1.MVector()
    view.viewToWorld(int(x), int(y), origin, direction)
    cam = (origin.x, origin.y, origin.z)
    best, best_d = None, radius
    for i, m in enumerate(S["markers"][side]):
        p = _project(view, m["pos"])
        if p is None:
            continue
        d = ((p[0] - x) ** 2 + (p[1] - y) ** 2) ** 0.5
        if d < best_d and not _occluded(side, m["pos"], cam):
            best, best_d = i, d
    return best



def _next_mid():
    S["mid"] = S.get("mid", 0) + 1
    return S["mid"]


def _pair(a, b):
    """Link two markers as each other's mirror, so moving one later moves the other."""
    if a.get("mid") is None:
        a["mid"] = _next_mid()
    if b.get("mid") is None:
        b["mid"] = _next_mid()
    a["twin"], b["twin"] = b["mid"], a["mid"]


def _mesh_span(side):
    """Rough size of the mesh, for a scale-independent match tolerance."""
    try:
        bb = cmds.exactWorldBoundingBox(S["mesh"][side])
        return max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]) or 1.0
    except Exception:
        return 1.0


def _twin_index(side, idx):
    """Index of the mirrored partner of marker `idx`, or None.

    Uses the link stored when the pair was placed; markers from an older session (or an
    imported file) have no link, so those fall back to 'nearest marker to the mirrored spot'."""
    mks = S["markers"][side]
    if not (0 <= idx < len(mks)):
        return None
    mk = mks[idx]
    tid = mk.get("twin")
    if tid is not None:
        for i, o in enumerate(mks):
            if i != idx and o.get("mid") == tid:
                return i
    if abs(mk["pos"][0]) < 1e-4:          # sits on the centre line - it is its own mirror
        return None
    tx, ty, tz = -mk["pos"][0], mk["pos"][1], mk["pos"][2]
    tol = (0.08 * _mesh_span(side)) ** 2
    best, best_d = None, None
    for i, o in enumerate(mks):
        if i == idx:
            continue
        d = (o["pos"][0] - tx) ** 2 + (o["pos"][1] - ty) ** 2 + (o["pos"][2] - tz) ** 2
        if d <= tol and (best_d is None or d < best_d):
            best, best_d = i, d
    return best


def delete_marker(side, idx):
    """Remove one marker - and its mirrored partner while Symmetry is on. The remaining
    markers renumber themselves, because the number shown is just the position in the list."""
    mks = S["markers"][side]
    if not (0 <= idx < len(mks)):
        return 0
    victims = {idx}
    if S.get("symmetry"):
        t = _twin_index(side, idx)
        if t is not None:
            victims.add(t)
    removed = [(side, mks[i], i) for i in sorted(victims)]
    for i in sorted(victims, reverse=True):
        del mks[i]
    S["history"].append({"kind": "delete", "items": removed})
    S["redo"] = []
    _update_overlays()
    ui._sync_action_btns()
    persist.save_to_scene()
    return len(removed)


def _on_drag():
    """Shift + left-drag: the picked marker follows the cursor over the mesh surface."""
    d = S.get("drag")
    if not d:
        return
    try:
        found = _pointer_view()
        if not found or found[0] != d["side"]:
            return
        side, panel, view, x, y = found
        origin, direction = om1.MPoint(), om1.MVector()
        view.viewToWorld(int(x), int(y), origin, direction)
        hit = _raycast(side, origin, direction)
        if not hit:
            return
        mk = S["markers"][side][d["idx"]]
        mk["pos"] = (hit[0].x, hit[0].y, hit[0].z)
        bind_marker(side, mk, point=om2.MPoint(hit[0].x, hit[0].y, hit[0].z),
                    face=hit[1], shape=hit[2])
        tw = d.get("twin")
        if tw is not None and 0 <= tw < len(S["markers"][side]):
            mirror = _mirror_point(side, mk["pos"])      # mirrored across X, snapped to the mesh
            if mirror:
                twin = S["markers"][side][tw]
                twin["pos"] = (mirror[0].x, mirror[0].y, mirror[0].z)
                bind_marker(side, twin, point=mirror[0], face=mirror[1], shape=mirror[2])
        _update_overlays()
    except Exception:
        import traceback
        traceback.print_exc()



def _on_release():
    d = S.get("drag")
    if not d:
        return
    S["drag"] = None
    snap_markers()                      # settle onto the surface before recording where it ended up
    moved = []
    for side, mk, before in d.get("before", []):
        after = state_of(mk)
        if after["pos"] != before["pos"]:
            moved.append((side, mk, before, after))
    if moved:                           # so Ctrl+Z puts a dragged marker back
        S["history"].append({"kind": "move", "items": moved})
        S["redo"] = []
    persist.save_to_scene()
    _update_overlays()
    ui._sync_action_btns()



def _on_press():
    try:
        f = QtWidgets.QApplication.focusWidget()
        if isinstance(f, QtWidgets.QLineEdit):
            f.clearFocus()
        found = _pointer_view()
        if found:
            side, panel, view, x, y = found
        else:  # fall back to Maya's own pointer / anchor queries
            panel = cmds.getPanel(underPointer=True) or cmds.getPanel(withFocus=True)
            side = next((sd for sd in ("A", "B") if S["panel"][sd] == panel), None)
            if not side:
                _notify("Click inside view A or view B to place a marker.")
                return
            x, y = cmds.draggerContext(CTX, q=True, anchorPoint=True)[:2]
            view = omui.M3dView()
            omui.M3dView.getM3dViewFromModelPanel(panel, view)
        # double-click brings hidden markers back (draggerContext has no double-click of its
        # own, so two presses close together in time and place count as one)
        now = time.time()
        last_t, last_xy = S.get("press_t", 0.0), S.get("press_xy")
        double = (now - last_t < 0.35 and last_xy is not None
                  and abs(x - last_xy[0]) < 8 and abs(y - last_xy[1]) < 8)
        S["press_t"], S["press_xy"] = now, (x, y)
        if S.get("hidden"):
            if double:
                ui._toggle_markers()
            else:
                _notify("Markers are hidden - double-click to bring them back.")
            return                              # never place a marker you cannot see

        if not S["mesh"][side] or not cmds.objExists(S["mesh"][side]):
            _notify("Load mesh %s first." % side)
            return
        S["drag"] = None
        try:
            mods = str(cmds.draggerContext(CTX, q=True, modifier=True) or "")
        except Exception:
            mods = ""
        low = mods.lower()
        if "ctrl" in low:                         # Ctrl + left mouse: delete the marker under the cursor
            idx = _pick_marker(side, view, x, y)
            if idx is None:
                _notify("Ctrl + click deletes a marker - put the cursor over one first.")
                return
            n = delete_marker(side, idx)
            _notify("Deleted %d marker%s on %s - the rest renumbered."
                    % (n, "" if n == 1 else "s", side))
            return
        if "shift" in low:                        # Shift + left mouse: move the marker under the cursor
            idx = _pick_marker(side, view, x, y)
            if idx is None:
                _notify("Shift + drag moves a marker - put the cursor over one first.")
                return
            twin = _twin_index(side, idx) if S.get("symmetry") else None
            mks = S["markers"][side]
            before = [(side, mks[idx], state_of(mks[idx]))]
            if twin is not None:
                before.append((side, mks[twin], state_of(mks[twin])))
            S["drag"] = {"side": side, "idx": idx, "twin": twin, "before": before}
            return
        origin, direction = om1.MPoint(), om1.MVector()
        view.viewToWorld(int(x), int(y), origin, direction)
        hit = _raycast(side, origin, direction)
        if not hit:
            _notify("Click missed mesh %s - click on the surface of the mesh." % side)
            return
        group = []
        first = _add_marker(side, hit[0], hit[1], hit[2], group=group)
        if S.get("symmetry") and abs(hit[0].x) > 1e-4:     # also place the mirrored marker on the same mesh
            mirror = _mirror_point(side, hit[0])
            if mirror:
                second = _add_marker(side, mirror[0], mirror[1], mirror[2], group=group)
                _pair(first, second)                        # so moving one later moves the other
            else:
                _notify("Symmetry: could not find a matching point on the other side.")
        _commit_group(group)
    except Exception:
        import traceback
        traceback.print_exc()
        _notify("Marker placement failed - see the Script Editor for the error.")
