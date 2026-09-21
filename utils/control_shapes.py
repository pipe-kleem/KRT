"""Auto-split from utils.py."""
from ._shared import *
from .paths import get_versioned_path


def export_control_shapes(file_path, controls=None, search_pattern=None):
    if search_pattern:
        found_controls = cmds.ls(search_pattern, type="transform")
        if not found_controls:
            cmds.warning("No controls found matching pattern: {}".format(search_pattern))
            return False
        controls = found_controls
    elif controls is None:
        controls = cmds.ls(selection=True)
        
    if not controls:
        cmds.warning("No controls selected or provided to export.")
        return False

    shape_dict = {}
    for ctrl in controls:
        shapes = cmds.listRelatives(ctrl, shapes=True, fullPath=True)
        if not shapes: continue 
        shape_dict[ctrl] = {}

        if cmds.attributeQuery("overrideEnabled", node=ctrl, exists=True) and cmds.getAttr(ctrl + ".overrideEnabled"):
            t_color_data = {'overrideEnabled': 1}
            if cmds.getAttr(ctrl + ".overrideRGBColors"):
                t_color_data['overrideRGBColors'] = 1
                t_color_data['overrideColorRGB'] = cmds.getAttr(ctrl + ".overrideColorRGB")[0]
            else:
                t_color_data['overrideRGBColors'] = 0
                t_color_data['overrideColor'] = cmds.getAttr(ctrl + ".overrideColor")
            shape_dict[ctrl]['__transform_color__'] = t_color_data

        for shape in shapes:
            # Support any shape type, not just mgear-style nurbsCurves:
            # meshes store vertices (.vtx[*]), curves/surfaces store CVs (.cv[*]).
            shp_type = cmds.nodeType(shape)
            comp = ".vtx[*]" if shp_type == "mesh" else ".cv[*]"
            pts = cmds.ls(shape + comp, flatten=True)
            if not pts:  # fall back to generic control points for exotic shapes
                pts = cmds.ls(shape + ".controlPoints[*]", flatten=True)
            point_positions = []
            for p in pts:
                pos = cmds.xform(p, query=True, translation=True, objectSpace=True)
                point_positions.append(pos)

            color_data = {}
            if cmds.attributeQuery("overrideEnabled", node=shape, exists=True) and cmds.getAttr(shape + ".overrideEnabled"):
                color_data['overrideEnabled'] = 1
                if cmds.getAttr(shape + ".overrideRGBColors"):
                    color_data['overrideRGBColors'] = 1
                    color_data['overrideColorRGB'] = cmds.getAttr(shape + ".overrideColorRGB")[0]
                else:
                    color_data['overrideRGBColors'] = 0
                    color_data['overrideColor'] = cmds.getAttr(shape + ".overrideColor")

            shape_dict[ctrl][shape.split('|')[-1]] = {
                'type': shp_type,
                'points': point_positions,
                'cvs': point_positions,  # legacy key kept for backward compatibility
                'color': color_data,
            }

    # Stage 48: write EXACTLY where the caller asked.
    #
    # This used to call get_versioned_path(file_path, get_latest=False) and
    # write to the bumped path instead, which quietly broke
    # "Save (Overwrite)": the panel passed the current file, this bumped it
    # to the next _vNNN, and the file the user meant to overwrite was never
    # touched. "Save (New Version)" appeared to work only because bumping an
    # already-bumped path still produces a new file (it just skipped a
    # number). Versioning is the caller's decision - SortablePanel.
    # save_versioned_data() already makes it.
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory): os.makedirs(directory)

    with open(file_path, 'w') as f: json.dump(shape_dict, f, indent=4)
    cmds.warning("SUCCESS: Exported {} controls to '{}'".format(len(shape_dict), file_path))
    return file_path

def import_control_shapes(file_path):
    # An exact path wins over version-hunting: now that Save (Overwrite)
    # really overwrites, loading has to read back the file that was written
    # rather than skipping to a higher _vNNN sitting next to it. Only when
    # the named file is absent do we fall back to the newest version.
    latest_file_path = file_path if os.path.isfile(file_path) else get_versioned_path(file_path, get_latest=True)
    if not os.path.exists(latest_file_path):
        om.MGlobal.displayError(f"File does not exist: {latest_file_path}")
        return False

    with open(latest_file_path, 'r') as f: shape_dict = json.load(f)
    applied_count = 0

    for ctrl, shapes_data in shape_dict.items():
        if not cmds.objExists(ctrl):
            continue

        if '__transform_color__' in shapes_data:
            t_color = shapes_data['__transform_color__']
            cmds.setAttr(ctrl + ".overrideEnabled", 1)
            if t_color.get('overrideRGBColors'):
                cmds.setAttr(ctrl + ".overrideRGBColors", 1)
                rgb = t_color.get('overrideColorRGB', [0,0,0])
                cmds.setAttr(ctrl + ".overrideColorRGB", rgb[0], rgb[1], rgb[2])
            else:
                cmds.setAttr(ctrl + ".overrideRGBColors", 0)
                cmds.setAttr(ctrl + ".overrideColor", t_color.get('overrideColor', 0))

        shape_items = [(k, v) for k, v in shapes_data.items() if k != '__transform_color__']
        current_shapes = cmds.listRelatives(ctrl, shapes=True, fullPath=True) or []
        used_targets = set()

        for i, (old_shape_name, data) in enumerate(shape_items):
            # Match the saved shape to a live shape by short name first, then fall
            # back to positional order. This keeps multi-shape controls correct.
            target_shape = None
            for cs in current_shapes:
                if cs in used_targets:
                    continue
                if cs.split('|')[-1] == old_shape_name:
                    target_shape = cs
                    break
            if target_shape is None and i < len(current_shapes):
                cand = current_shapes[i]
                if cand not in used_targets:
                    target_shape = cand
            if target_shape is None:
                continue
            used_targets.add(target_shape)

            # Positions work for any point count and any shape type: meshes use
            # vertices, everything else uses CVs.
            positions = data.get('points')
            if positions is None:
                positions = data.get('cvs', [])
            shp_type = data.get('type') or cmds.nodeType(target_shape)
            comp = "vtx" if shp_type == "mesh" else "cv"

            for j, pos in enumerate(positions):
                cv_path = "{}.{}[{}]".format(target_shape, comp, j)
                if cmds.objExists(cv_path):
                    cmds.xform(cv_path, translation=pos, objectSpace=True)

            color_data = data.get('color', {})
            if color_data.get('overrideEnabled'):
                cmds.setAttr(target_shape + ".overrideEnabled", 1)
                if color_data.get('overrideRGBColors'):
                    cmds.setAttr(target_shape + ".overrideRGBColors", 1)
                    rgb = color_data.get('overrideColorRGB', [0,0,0])
                    cmds.setAttr(target_shape + ".overrideColorRGB", rgb[0], rgb[1], rgb[2])
                else:
                    cmds.setAttr(target_shape + ".overrideRGBColors", 0)
                    cmds.setAttr(target_shape + ".overrideColor", color_data.get('overrideColor', 0))
            applied_count += 1

    cmds.warning("SUCCESS: Imported shapes for {} controls from '{}'".format(applied_count, latest_file_path))
    return True


def find_guide_model(start_node):
    """Walk up from any node inside an mGear guide to the top-level guide
    model transform (mGear marks it with an "ismodel" attribute - this is
    the same node mGear's own guide.model points to). Returns the long name,
    or None if start_node isn't (inside) a guide at all."""
    walker = start_node
    while walker:
        if cmds.attributeQuery("ismodel", node=walker, exists=True):
            return walker
        parents = cmds.listRelatives(walker, parent=True, fullPath=True)
        walker = parents[0] if parents else None
    return None


def apply_control_shapes_library(library_path, guide_model):
    """Merge the '*_controlBuffer' curves found in an external Maya scene
    file into `guide_model`'s own "controllers_org" group, so mGear's own
    build step (Component.addCtl) shapes each matching control from them
    automatically - this is exactly mGear's native hand-authored control
    buffer mechanism (see shifter/__init__.py addCtl: it looks up
    "<control_name>_controlBuffer" in the guide's controllers dict and, if
    found, moves that buffer curve's shape onto the freshly built control
    instead of using the component's default icon shape). This function
    just sources those buffer curves from a shared external file instead of
    requiring them to be hand-authored in every guide.

    Must be called AFTER the guide (and its controllers_org group, created
    by mGear's initialHierarchy) exists, and BEFORE buildFromSelection()/
    build() runs for it - mGear only reads controllers_org once, right at
    the start of the build.

    Args:
        library_path (str): path to a .ma/.mb file containing one or more
            transforms named "<something>_controlBuffer" (anywhere in its
            hierarchy - everything else in the file is ignored and discarded).
        guide_model (str): long name of the guide's top-level model
            transform (e.g. from find_guide_model() or mgear's rig_guide.model).

    Returns:
        int: number of buffer curves applied (0 if nothing happened).
    """
    if not library_path or not os.path.exists(library_path):
        if library_path:
            cmds.warning("Control Shapes Library not found: {}".format(library_path))
        return 0
    if not guide_model or not cmds.objExists(guide_model):
        return 0

    controllers_org = None
    for child in cmds.listRelatives(guide_model, children=True, fullPath=True) or []:
        if child.split("|")[-1] == "controllers_org":
            controllers_org = child
            break
    if not controllers_org:
        # mGear always creates this in initialHierarchy(); guard anyway so a
        # hand-built or unusual guide doesn't just silently no-op.
        controllers_org = cmds.group(name="controllers_org", empty=True, parent=guide_model)
        cmds.setAttr(controllers_org + ".visibility", 0)

    ns = "KRT_CTLSHAPES_TMP"
    n = 1
    while cmds.namespace(exists=ns):
        ns = "KRT_CTLSHAPES_TMP{}".format(n)
        n += 1

    try:
        imported = cmds.file(library_path, i=True, namespace=ns, ignoreVersion=True,
                              mergeNamespacesOnClash=False, preserveReferences=False,
                              returnNewNodes=True) or []
    except Exception:
        traceback.print_exc()
        cmds.warning("Failed to import Control Shapes Library '{}' - see Script Editor.".format(library_path))
        return 0

    applied = 0
    try:
        existing = {c.split("|")[-1]: c for c in
                    (cmds.listRelatives(controllers_org, children=True, fullPath=True) or [])}

        for node in imported:
            if not cmds.objExists(node) or cmds.nodeType(node) != "transform":
                continue
            short = node.split("|")[-1].split(":")[-1]
            if not short.endswith("_controlBuffer"):
                continue

            # Drop any buffer of the same name already sitting under
            # controllers_org BEFORE renaming the incoming one into its
            # place, so Maya doesn't auto-uniquify the new name instead.
            old = existing.get(short)
            if old and cmds.objExists(old):
                try:
                    cmds.delete(old)
                except Exception:
                    pass

            try:
                clean = cmds.rename(node, short)
                clean = cmds.parent(clean, controllers_org)[0]
                applied += 1
            except Exception:
                continue
    finally:
        # Anything left behind from the import - the library file's own
        # "guide"/"controllers_org" grouping, unrelated locators/roots, etc -
        # isn't a buffer curve and was never moved out, so it's still sitting
        # under its original namespaced name: sweep it away, then the
        # now-empty temp namespace.
        leftovers = [n for n in imported if cmds.objExists(n)]
        if leftovers:
            try:
                cmds.delete(leftovers)
            except Exception:
                pass
        try:
            if cmds.namespace(exists=ns):
                cmds.namespace(removeNamespace=ns, mergeNamespaceWithRoot=True)
        except Exception:
            pass

    if applied:
        cmds.warning("Control Shapes Library: applied {} buffer curve(s) from '{}'.".format(applied, library_path))
    return applied
