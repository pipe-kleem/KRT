"""Wrap the view B mesh with the generated marker mesh, so the Offset slider deforms it too.

Built by hand rather than through MEL's doWrapArgList, so every setting that can make a wrap
hang Maya is chosen deliberately:
  * the driver is the generated marker mesh (a handful of faces), never a dense mesh
  * the base ("rest") shape is taken with the blendshape at 0, so nothing jumps on creation
  * binding happens inside one undo chunk, with the viewports paused, and is undoable in one step
  * a heavy target is flagged before anything is built, not after Maya has already locked up
"""
from .state import S, cmds
from . import ui, views

WRAP = "wrapMarkerWrapNode"
BASE = "wrapMarkerWrapBase"
HEAVY = 400000           # target vertices above which we ask first


def _shape(node):
    sh = views._mesh_shapes(node) if node else []
    return sh[0] if sh else None


def find_wrap():
    """The wrap deformer this tool made, if it is still in the scene."""
    for n in cmds.ls(WRAP + "*", type="wrap") or []:
        return n
    return None


def has_wrap():
    return find_wrap() is not None


def _vertex_count(node):
    try:
        return sum(cmds.polyEvaluate(sh, vertex=True) for sh in views._mesh_shapes(node))
    except Exception:
        return 0


def _set_blend_weight(value):
    """Set the generated blendshape weight without touching S['blend'] (returns the old value)."""
    bs = S["gen"].get("bs")
    if not (bs and cmds.objExists(bs)):
        return None
    try:
        old = cmds.getAttr(bs + ".weight[0]")
        cmds.setAttr(bs + ".weight[0]", value)
        return old
    except Exception:
        return None


def _driver_attrs(driver):
    """The three attributes a wrap expects to read off its driver."""
    for ln, sn, kw in (("dropoff", "dr", dict(dv=4.0, min=0.0, max=20.0)),
                       ("smoothness", "smt", dict(dv=0.0, min=0.0)),
                       ("inflType", "ift", dict(at="short", dv=2, min=1, max=2))):
        if not cmds.attributeQuery(ln, node=driver, exists=True):
            cmds.addAttr(driver, longName=ln, shortName=sn, **kw)
        try:
            cmds.setAttr(driver + "." + ln, keyable=True)
        except Exception:
            pass


def create_wrap(*_):
    """Wrap mesh B with the generated mesh."""
    driver = S["gen"].get("base")
    target = S["mesh"].get("B")
    if not (driver and cmds.objExists(driver)):
        cmds.warning("Create the marker mesh first - that is what does the wrapping.")
        return
    if not (target and cmds.objExists(target)):
        cmds.warning("Load a mesh into view B first.")
        return
    if has_wrap():
        cmds.warning("Mesh B is already wrapped.")
        return
    d_shape, t_shape = _shape(driver), _shape(target)
    if not (d_shape and t_shape):
        cmds.warning("Could not find a mesh shape to wrap.")
        return

    n = _vertex_count(target)
    if n > HEAVY and cmds.confirmDialog(
            title="Wrap mesh B",
            message="Mesh B has %s vertices. Binding a wrap that heavy can take a while and\n"
                    "Maya will not respond until it finishes.\n\nGo ahead?" % format(n, ","),
            button=["Wrap", "Cancel"], defaultButton="Cancel",
            cancelButton="Cancel", dismissString="Cancel") != "Wrap":
        return

    ui.message("Binding the wrap - Maya may pause for a moment...")
    try:
        cmds.refresh()
    except Exception:
        pass

    old_weight = _set_blend_weight(0.0)      # bind against the rest shape, so nothing jumps
    paused = False
    try:
        cmds.refresh(suspend=True)           # no viewport redraws while we build it
        paused = True
    except Exception:
        pass
    cmds.undoInfo(openChunk=True, chunkName="wrapMarkerWrapB")
    try:
        base = cmds.duplicate(driver, name=BASE, returnRootsOnly=True)[0]
        for a in ("translate", "rotate", "scale"):
            for ax in "XYZ":
                try:
                    cmds.setAttr("%s.%s%s" % (base, a, ax), lock=False)
                except Exception:
                    pass
        try:
            cmds.setAttr(base + ".visibility", 0)
        except Exception:
            pass
        b_shape = _shape(base)

        wrap = cmds.deformer(target, type="wrap", name=WRAP)[0]
        # settings chosen for speed and for a sparse driver:
        cmds.setAttr(wrap + ".exclusiveBind", 0)        # smooth, not chunky
        cmds.setAttr(wrap + ".autoWeightThreshold", 1)  # every target point keeps a sane weight
        cmds.setAttr(wrap + ".maxDistance", 0)          # no search radius to blow up on
        cmds.setAttr(wrap + ".falloffMode", 0)
        cmds.setAttr(wrap + ".envelope", 1)

        _driver_attrs(driver)
        cmds.connectAttr(driver + ".dropoff", wrap + ".dropoff[0]", force=True)
        cmds.connectAttr(driver + ".smoothness", wrap + ".smoothness[0]", force=True)
        cmds.connectAttr(driver + ".inflType", wrap + ".inflType[0]", force=True)
        cmds.connectAttr(d_shape + ".worldMesh[0]", wrap + ".driverPoints[0]", force=True)
        cmds.connectAttr(b_shape + ".worldMesh[0]", wrap + ".basePoints[0]", force=True)
        cmds.connectAttr(target + ".worldMatrix[0]", wrap + ".geomMatrix", force=True)
    except Exception as e:
        cmds.undoInfo(closeChunk=True)
        if paused:
            try:
                cmds.refresh(suspend=False)
            except Exception:
                pass
        delete_wrap(quiet=True)
        if old_weight is not None:
            _set_blend_weight(old_weight)
        import traceback
        traceback.print_exc()
        cmds.warning("Could not wrap mesh B: %s" % e)
        return
    finally:
        cmds.undoInfo(closeChunk=True)

    if paused:
        try:
            cmds.refresh(suspend=False)
        except Exception:
            pass
    if old_weight is not None:
        _set_blend_weight(old_weight)
    ui._sync_wrap_btn()
    ui.message("Mesh B is wrapped - move the Offset slider and it follows the marker mesh.")


def delete_wrap(quiet=False, *_):
    """Remove the wrap and its base mesh, leaving mesh B as it was."""
    gone = []
    for n in (cmds.ls(WRAP + "*", type="wrap") or []):
        try:
            cmds.delete(n)
            gone.append(n)
        except Exception as e:
            cmds.warning("Could not delete %s: %s" % (n, e))
    for n in (cmds.ls(BASE + "*", transforms=True) or []):
        try:
            cmds.delete(n)
        except Exception:
            pass
    try:
        ui._sync_wrap_btn()
    except Exception:
        pass
    if gone and not quiet:
        ui.message("Wrap removed - mesh B is back to normal.")
    return bool(gone)


def toggle_wrap(*_):
    if has_wrap():
        delete_wrap()
    else:
        create_wrap()
