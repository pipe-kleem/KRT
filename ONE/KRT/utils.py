import maya.cmds as cmds
import maya.OpenMaya as om
import os
import json
import re

def get_versioned_path(file_path, get_latest=False):
    directory = os.path.dirname(file_path)
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    base_name = re.sub(r'_v\d+$', '', base_name)
    
    if not os.path.exists(directory):
        if get_latest: return file_path 
        return os.path.join(directory, "{}_v001{}".format(base_name, ext)).replace('\\', '/')

    highest_version = 0
    pattern = re.compile(r"^{}_v(\d+){}$".format(re.escape(base_name), re.escape(ext)))

    if os.path.exists(directory):
        for f in os.listdir(directory):
            match = pattern.match(f)
            if match:
                version = int(match.group(1))
                if version > highest_version:
                    highest_version = version

    if get_latest:
        if highest_version == 0: return file_path
        latest_name = "{}_v{:03d}{}".format(base_name, highest_version, ext)
        return os.path.join(directory, latest_name).replace('\\', '/')
    else:
        next_version = highest_version + 1
        new_name = "{}_v{:03d}{}".format(base_name, next_version, ext)
        return os.path.join(directory, new_name).replace('\\', '/')

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

    versioned_file_path = get_versioned_path(file_path, get_latest=False)
    directory = os.path.dirname(versioned_file_path)
    if directory and not os.path.exists(directory): os.makedirs(directory)

    with open(versioned_file_path, 'w') as f: json.dump(shape_dict, f, indent=4)
    cmds.warning("SUCCESS: Exported {} controls to '{}'".format(len(shape_dict), versioned_file_path))
    return versioned_file_path

def import_control_shapes(file_path):
    latest_file_path = get_versioned_path(file_path, get_latest=True)
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