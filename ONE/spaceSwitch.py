
def space_switch(target, drivers, attr_name="spaceSwitch", include_local=True):
    # 1. Get current parent of target control to preserve hierarchy
    orig_parent = cmds.listRelatives(target, parent=True)
    orig_parent = orig_parent[0] if orig_parent else None

    # 2. Always create a new dedicated offset group for space switching
    space_grp = cmds.group(em=True, name=f"{target}_space_grp")
    cmds.matchTransform(space_grp, target)

    # Insert the new group above target in the hierarchy
    if orig_parent:
        cmds.parent(space_grp, orig_parent)
    cmds.parent(target, space_grp)

    # 3. Setup spaces list including default 'Local' option
    spaces = (["Local"] if include_local else []) + drivers

    # 4. Add Enum attribute to target control
    if not cmds.attributeQuery(attr_name, node=target, exists=True):
        cmds.addAttr(target, ln=attr_name, at="enum", en=":".join(spaces), k=True)

    # 5. Create parent constraint ON THE NEW SPACE GROUP
    constraint = cmds.orientConstraint(drivers, space_grp, mo=True)[0]
    weights = cmds.orientConstraint(constraint, q=True, wal=True)

    # 6. Connect Enum to constraint weights via Set Driven Keys
    for i, driver in enumerate(drivers):
        weight_attr = f"{constraint}.{weights[i]}"
        active_idx = i + 1 if include_local else i
        
        for idx in range(len(spaces)):
            cmds.setAttr(f"{target}.{attr_name}", idx)
            cmds.setAttr(weight_attr, 1.0 if idx == active_idx else 0.0)
            cmds.setDrivenKeyframe(weight_attr, cd=f"{target}.{attr_name}")

    cmds.setAttr(f"{target}.{attr_name}", 0)



space_switch("spine_C0_ik1_ctl", [ "world_ctl", "body_C0_ctl"], include_local=True)