"""Save / restore markers: automatically inside the Maya scene, and manually as a .json file."""
import json
import os

from .state import DATA_ATTR, S, cmds

STORE = "wrapMarkerStore"      # small network node that keeps the live marker data inside the scene
FORMAT = "wrapMarker-markers-v1"


def _short(x):
    return x.split("|")[-1] if x else None


def _resolve(name):
    if not name:
        return None
    try:
        found = cmds.ls(name, long=True) or []
    except Exception:
        return None
    return found[0] if found else None


def collect():
    """The current markers as a plain, json-ready dict."""
    def side(s):
        return [{"id": i + 1, "pos": [float(c) for c in m["pos"]], "face": int(m["face"]),
                 "shape": _short(m.get("shape")),
                 "mid": m.get("mid"), "twin": m.get("twin"),      # mirror pairing, kept across sessions
                 "bind": m.get("bind")}                           # which triangle it is stuck to
                for i, m in enumerate(S["markers"][s])]
    return {"format": FORMAT, "meshA": _short(S["mesh"]["A"]), "meshB": _short(S["mesh"]["B"]),
            "A": side("A"), "B": side("B")}


# ------------------------------------------------------------------ inside the scene
def save_to_scene():
    """Keep the markers in the scene (a 'network' node), so the next time the tool opens they come back."""
    if S.get("restoring"):
        return
    try:
        cmds.undoInfo(stateWithoutFlush=False)      # never pollute the user's undo queue
        try:
            empty = not (S["markers"]["A"] or S["markers"]["B"])
            if empty:
                if cmds.objExists(STORE):
                    cmds.delete(STORE)
                return
            if not cmds.objExists(STORE):
                cmds.createNode("network", name=STORE)
            if not cmds.attributeQuery(DATA_ATTR, node=STORE, exists=True):
                cmds.addAttr(STORE, longName=DATA_ATTR, dataType="string")
            cmds.setAttr(STORE + "." + DATA_ATTR, json.dumps(collect()), type="string")
        finally:
            cmds.undoInfo(stateWithoutFlush=True)
    except Exception as e:
        print("wrapMarker: could not keep the markers in the scene: %s" % e)


def delete_store():
    try:
        if cmds.objExists(STORE):
            cmds.delete(STORE)
    except Exception:
        pass


def _from_gen_mesh(data):
    """Marker data written onto the generated mesh by 'Create Mesh' (pairs format) -> A/B lists."""
    pairs = sorted(data.get("pairs", []), key=lambda p: p["id"])
    A = [dict(p["A"]) for p in pairs] + [dict(u) for u in data.get("unpairedA", [])]
    B = [dict(p["B"]) for p in pairs] + [dict(u) for u in data.get("unpairedB", [])]
    return {"meshA": data.get("meshA"), "meshB": data.get("meshB"), "A": A, "B": B}


def _find_scene_data():
    """(data, where) from the store node, else from a mesh generated earlier by this tool."""
    if cmds.objExists(STORE) and cmds.attributeQuery(DATA_ATTR, node=STORE, exists=True):
        try:
            return json.loads(cmds.getAttr(STORE + "." + DATA_ATTR)), "the scene"
        except Exception:
            pass
    for n in (cmds.ls("wrapMarkerMesh*", "wrapSmoothA*", type="transform") or []):
        try:
            if cmds.attributeQuery(DATA_ATTR, node=n, exists=True):
                d = json.loads(cmds.getAttr(n + "." + DATA_ATTR))
                if d.get("pairs") or d.get("unpairedA") or d.get("unpairedB"):
                    return _from_gen_mesh(d), "the generated mesh '%s'" % n
        except Exception:
            continue
    return None, None


def _side_groups(side):
    """Markers of one side as undo steps, mirrored pairs kept together, in placement order."""
    mks = S["markers"][side]
    by_mid = {m["mid"]: m for m in mks if m.get("mid") is not None}
    seen, groups = set(), []
    for mk in mks:
        if id(mk) in seen:
            continue
        seen.add(id(mk))
        grp = [(side, mk)]
        twin = by_mid.get(mk.get("twin"))
        if twin is not None and id(twin) not in seen:
            seen.add(id(twin))
            grp.append((side, twin))
        groups.append(grp)
    return groups


def _seed_history():
    """Give imported / restored markers an undo history, so Ctrl+Z removes them too.

    A and B are interleaved so undoing peels them off in step and the pair count stays
    balanced (Create Mesh only uses as many pairs as the shorter side has)."""
    a, b = _side_groups("A"), _side_groups("B")
    history = []
    for i in range(max(len(a), len(b))):
        if i < len(a):
            history.append({"kind": "add", "items": a[i]})
        if i < len(b):
            history.append({"kind": "add", "items": b[i]})
    return history


def apply(data):
    """Put marker data into the tool (meshes are taken from the scene by name). Returns (nA, nB)."""
    from . import markers, ui, views
    if "pairs" in data:
        data = _from_gen_mesh(data)
    S["restoring"] = True
    try:
        for side in ("A", "B"):
            name = data.get("mesh" + side)
            node = _resolve(name)
            if node and S["mesh"][side] != node:
                views._assign_mesh(side, node)
            elif name and not node:
                cmds.warning("Markers file: mesh %s '%s' is not in the scene - load it, then import again."
                             % (side, name))
            out = []
            if S["mesh"][side]:
                shapes = views._mesh_shapes(S["mesh"][side])
                for m in data.get(side, []):
                    shp = _resolve(m.get("shape")) or (shapes[0] if shapes else None)
                    if shp:
                        mk = {"pos": tuple(m["pos"]), "face": int(m["face"]), "shape": shp}
                        if m.get("mid") is not None:
                            mk["mid"] = m["mid"]
                        if m.get("twin") is not None:
                            mk["twin"] = m["twin"]
                        bind = m.get("bind")
                        if bind and bind.get("tri") and bind.get("w"):
                            b_shape = _resolve(bind.get("shape")) or shp
                            mk["bind"] = {"shape": b_shape, "tri": list(bind["tri"]),
                                          "w": list(bind["w"])}
                        out.append(mk)
            S["markers"][side] = out
        S["history"], S["redo"] = _seed_history(), []
        # keep new markers from reusing a restored pair id
        ids = [mk.get("mid") or 0 for sd in ("A", "B") for mk in S["markers"][sd]]
        S["mid"] = max([S.get("mid", 0)] + ids)
        # re-adopt a generated mesh that is still in the scene
        g = S["gen"]
        if not g["base"] and cmds.objExists("wrapMarkerMesh"):
            g["base"] = "wrapMarkerMesh"
            if cmds.objExists("wrapMarkerBlend"):
                g["bs"] = "wrapMarkerBlend"
            g["sig"] = None      # built by an earlier session: treat as out of date, so the
                                 # button offers "Update Mesh" and rebuilds from ALL markers
    finally:
        S["restoring"] = False
    markers._update_overlays()
    try:
        ui._sync_action_btns()
    except Exception:
        pass
    ui._update_statusbar()
    return len(S["markers"]["A"]), len(S["markers"]["B"])


def restore_from_scene():
    """Called when the tool opens: take the markers that are already in the scene."""
    data, where = _find_scene_data()
    if not data:
        return False
    nA, nB = apply(data)
    if nA or nB:
        msg = "Restored %d markers on A and %d on B from %s." % (nA, nB, where)
        print("wrapMarker: " + msg)
        from . import ui
        sb = ui._ok("statusbar")
        if sb:
            cmds.text(sb, e=True, label="  " + msg)
        save_to_scene()
    return bool(nA or nB)


# ------------------------------------------------------------------ .json files
def save_file(*_):
    if not (S["markers"]["A"] or S["markers"]["B"]):
        cmds.warning("There are no markers to save.")
        return
    res = cmds.fileDialog2(fileMode=0, caption="Save markers", fileFilter="Markers (*.json)",
                           dialogStyle=2, okCaption="Save")
    if not res:
        return
    path = res[0]
    if not path.lower().endswith(".json"):
        path += ".json"
    with open(path, "w") as f:
        json.dump(collect(), f, indent=2)
    msg = "Saved %d + %d markers to %s" % (len(S["markers"]["A"]), len(S["markers"]["B"]), path)
    print("wrapMarker: " + msg)
    from . import ui
    sb = ui._ok("statusbar")
    if sb:
        cmds.text(sb, e=True, label="  " + msg)


def load_file(*_):
    res = cmds.fileDialog2(fileMode=1, caption="Import markers", fileFilter="Markers (*.json)",
                           dialogStyle=2, okCaption="Import")
    if not res:
        return
    with open(res[0], "r") as f:
        data = json.load(f)
    if not (("A" in data and "B" in data) or "pairs" in data):
        cmds.warning("That file has no markers (expected a file saved by 'Save Markers').")
        return
    have = len(S["markers"]["A"]) + len(S["markers"]["B"])
    if have and cmds.confirmDialog(title="Import markers",
                                   message="Replace the %d markers currently placed?" % have,
                                   button=["Replace", "Cancel"], defaultButton="Cancel",
                                   cancelButton="Cancel", dismissString="Cancel") != "Replace":
        return
    nA, nB = apply(data)
    save_to_scene()
    msg = "Imported %d markers on A and %d on B from %s" % (nA, nB, os.path.basename(res[0]))
    print("wrapMarker: " + msg)
    from . import ui
    sb = ui._ok("statusbar")
    if sb:
        cmds.text(sb, e=True, label="  " + msg)
