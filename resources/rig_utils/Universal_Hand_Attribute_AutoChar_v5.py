# =============================================================================
# UNIVERSAL HAND ATTRIBUTE BUILDER — COMBINED 14-STEP MAYA SCRIPT
# =============================================================================
#
# This file combines your 14 separate scripts into one reusable builder.
#
# HOW TO USE FOR ANOTHER CHARACTER
# --------------------------------
# 1. No manual CHAR change is required.
# 2. The character prefix is detected from the character *_a world group; generic rig_a is ignored.
#    Example top group: sanjay_a
#    Detected CHAR: sanjay_a
#    Result controls:
#       sanjay_a_Hand_Attribute_L_ctl
#       sanjay_a_Hand_Attribute_L_ctl_grp
# 3. Check SIDE_SETUP only if the rig uses different snap or arm-end names.
# 4. Keep BUILD_SIDES = ("L", "R") for both hands.
# 5. Run the complete file in Maya's Python tab.
#
# IMPORTANT:
# The hand attribute control group stays at WORLD level.
# It is NOT parented under any joint. A constraint is used so it can still
# follow the arm-end joint without changing the DAG hierarchy.
#
# FIRST BUILD / REBUILD
# ---------------------
# REBUILD_ATTRIBUTE_CONTROLS = True
#     Deletes and rebuilds the two hand attribute controls.
#
# REBUILD_ATTRIBUTE_CONTROLS = False
#     Keeps existing controls and animation, and only adds missing attributes.
#
# RUN ONLY SELECTED STEPS
# -----------------------
# RUN_STEPS = list(range(1, 15))    # Run all 14 steps
# RUN_STEPS = [6]                   # Rebuild only Fist
# RUN_STEPS = [11, 12, 13]          # Rebuild only spread attributes
#
# IMPORTANT
# ---------
# Step 1 must exist before attribute connection steps can work.
# Step 2 must exist before steps 3–14 can connect to the upper groups.
#
# =============================================================================

import maya.cmds as cmds


# =============================================================================
# A. MAIN USER SETTINGS — CHANGE THESE FOR ANOTHER CHARACTER
# =============================================================================

# Character base name is filled automatically by detect_character_prefix().
# Example: top group "sanjay_a" -> CHAR = "sanjay_a".
CHAR = None

# Build left, right, or both sides.
BUILD_SIDES = ("L", "R")

# Run all fourteen numbered steps.
RUN_STEPS = list(range(1, 15))

# True: delete and recreate the hand attribute controls.
# False: preserve existing controls and add only missing attributes.
REBUILD_ATTRIBUTE_CONTROLS = True

# Select the two hand attribute controls after the build finishes.
SELECT_FINISHED_CONTROLS = True

# Print detailed connection information in Maya's Script Editor.
VERBOSE = True


# Side-specific base nodes.
# snap  = used to place/orient the hand attribute control.
# joint = constraint driver only; the new control group is NOT parented to it.
SIDE_SETUP = {
    "L": {
        "snap": "finger_L1_fk2_ctl",
        "joint": "arm_L0_end_jnt",
        "color": 13,  # Maya red
    },
    "R": {
        "snap": "finger_R1_fk2_ctl",
        "joint": "arm_R0_end_jnt",
        "color": 6,   # Maya blue
    },
}


# =============================================================================
# B. RIG NAMING TEMPLATES
# =============================================================================
#
# Most future rig-name changes can be handled here.
#
# Available format keys:
# {char}, {side}, {finger}, {fk}, {base}, {suffix}
#
# Finger numbers:
# 0 = Index
# 1 = Middle
# 2 = Ring
# 3 = Pinky
#
# FK numbers:
# 0 = first finger control
# 1 = second finger control
# 2 = third finger control
#
# =============================================================================

NAME_TEMPLATES = {
    "hand_ctrl": "{char}_Hand_Attribute_{side}_ctl",
    "hand_ctrl_group": "{char}_Hand_Attribute_{side}_ctl_grp",

    "meta_ctrl": "meta_{side}0_meta{finger}_ctl",
    "meta_offset": "meta_{side}0_{finger}_loc",

    "finger_ctrl": "finger_{side}{finger}_fk{fk}_ctl",
    "finger_offset": "finger_{side}{finger}_fk{fk}_npo",

    "thumb_ctrl": "thumb_{side}0_fk{fk}_ctl",
    "thumb_offset": "thumb_{side}0_fk{fk}_npo",

    "upper_group": "{base}_{suffix}_ctl_grp",
}


# =============================================================================
# C. ATTRIBUTE LIST AND GROUP ORDER
# =============================================================================

# The order below is the order shown in Maya's Channel Box.
ATTRIBUTES = [
    ("Thumb", "bool"),
    ("Thumb_Curl_0", "double"),
    ("Thumb_Curl_1", "double"),
    ("Thumb_Curl_2", "double"),

    ("Index", "bool"),
    ("Index_Curl_0", "double"),
    ("Index_Curl_1", "double"),
    ("Index_Curl_2", "double"),
    ("Index_Curl_3", "double"),

    ("Middle", "bool"),
    ("Middle_Curl_0", "double"),
    ("Middle_Curl_1", "double"),
    ("Middle_Curl_2", "double"),
    ("Middle_Curl_3", "double"),

    ("Ring", "bool"),
    ("Ring_Curl_0", "double"),
    ("Ring_Curl_1", "double"),
    ("Ring_Curl_2", "double"),
    ("Ring_Curl_3", "double"),

    ("Pinky", "bool"),
    ("Pinky_Curl_0", "double"),
    ("Pinky_Curl_1", "double"),
    ("Pinky_Curl_2", "double"),
    ("Pinky_Curl_3", "double"),

    ("Hand", "bool"),
    ("Cup_1", "double"),
    ("Cup_2", "double"),
    ("Cup_3", "double"),
    ("Spread_A", "double"),
    ("Spread_B", "double"),
    ("Spread_Thumb", "double"),
    ("Nice_A", "double"),
    ("Nice_B", "double"),
    ("Scrunch_1", "double"),
    ("Scrunch_2", "double"),
    ("Fist", "double"),
]

# These Boolean attributes are visual section headers in the Channel Box.
HEADER_ATTRIBUTES = (
    "Thumb",
    "Index",
    "Middle",
    "Ring",
    "Pinky",
    "Hand",
)

# Upper groups are nested in this exact order.
UPPER_GROUP_SUFFIXES = (
    "Cup1",
    "Cup2",
    "Cup3",
    "Spread_A",
    "Spread_B",
    "Nice_A",
    "Nice_B",
    "Scrunch_1",
    "Scrunch_2",
    "Fist",
    "Curl",
)


# =============================================================================
# D. MOTION VALUES — EASY PLACE TO ADJUST HAND BEHAVIOR
# =============================================================================

# Step 3: Cup 1
CUP1_PINKY_MULTIPLIER = 1.00
CUP1_RING_MULTIPLIER = 0.40

# Step 6: Fist
# A Fist value of 100 produces:
# main fingers Z = 60, thumb FK0 Y = 15, thumb FK0 Z = 22,
# thumb FK1/FK2 Z = 15.
FIST_MAIN_MULTIPLIER = 0.60
FIST_THUMB_FK0_Y_MULTIPLIER = 0.15
FIST_THUMB_FK0_Z_MULTIPLIER = 0.22
FIST_THUMB_FK1_Z_MULTIPLIER = 0.15
FIST_THUMB_FK2_Z_MULTIPLIER = 0.15

# Step 7: Nice A — Index, Middle, Ring, Pinky
NICE_A_MULTIPLIERS = (-1.00, -0.30, 0.30, 1.00)

# Step 8: Nice B
NICE_B_POSITIVE = {
    3: 1.00,  # Pinky
    2: 0.50,  # Ring
    1: 0.25,  # Middle
    0: 0.12,  # Index
}
NICE_B_NEGATIVE = {
    3: 0.12,  # Pinky
    2: 0.25,  # Ring
    1: 0.50,  # Middle
    0: 1.00,  # Index
}

# Step 9: Scrunch 1
SCRUNCH1_FK0_MULTIPLIER = -0.50
SCRUNCH1_FK1_MULTIPLIERS = (0.80, 0.70, 0.70, 0.60)
SCRUNCH1_FK2_MULTIPLIER = 0.50

# Step 10: Scrunch 2
SCRUNCH2_FK_MULTIPLIERS = {
    0: -0.40,
    1: 1.10,
    2: -0.50,
}

# Step 11 and 12: Spread
SPREAD_RING_MULTIPLIER = 0.50


# =============================================================================
# E. GENERAL HELPER FUNCTIONS
# =============================================================================

def log(message):
    """Print detailed messages only when VERBOSE is enabled."""
    if VERBOSE:
        print(message)


def print_step(number, title):
    """Print a clear heading for each of the fourteen build steps."""
    print("\n" + "=" * 72)
    print("STEP {:02d}: {}".format(number, title))
    print("=" * 72)


def leaf_name(node):
    """Return a short Maya node name without DAG path or namespace."""
    short_name = node.split("|")[-1]
    return short_name.split(":")[-1]


def find_scene_nodes_by_leaf(leaf):
    """
    Find both non-namespaced and namespaced nodes whose leaf name matches.
    Full DAG paths are returned to avoid ambiguity.
    """
    found = []

    for pattern in (leaf, "*:" + leaf):
        for node in cmds.ls(pattern, long=True) or []:
            if leaf_name(node) == leaf and node not in found:
                found.append(node)

    return found


def top_transform(node):
    """Walk upward from node and return its highest DAG transform."""
    matches = cmds.ls(node, long=True) or []

    if not matches:
        return None

    current = matches[0]

    while True:
        parent = cmds.listRelatives(
            current,
            parent=True,
            fullPath=True
        ) or []

        if not parent:
            break

        current = parent[0]

    return current


def selected_top_group():
    """
    If the user has something selected, return that selection's top group.
    This is used only as a hint when multiple character rigs exist.
    """
    selection = cmds.ls(selection=True, long=True) or []

    if not selection:
        return None

    return top_transform(selection[0])


# Generic rig roots that must NEVER be used as the character name.
# Add more names here if your rig has other technical world groups.
IGNORE_AUTO_CHAR_TOP_GROUPS = {
    "rig_a",
}


def is_world_group(node):
    """Return True when node is a top-level transform group with no shape."""
    if not node or not cmds.objExists(node):
        return False

    parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
    if parents:
        return False

    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    return not shapes


def scene_character_top_groups():
    """
    Find character top groups at world level.

    Character group rule:
        - transform group at world level
        - full group name ends with "_a"
        - NOT a generic technical group such as "rig_a"

    Example:
        sanjay_a  -> valid
        vasu_a    -> valid
        rig_a     -> ignored
    """
    result = []

    for node in cmds.ls(assemblies=True, long=True, type="transform") or []:
        if not is_world_group(node):
            continue

        name = leaf_name(node)
        short_name = name.split(":")[-1]

        if not short_name.endswith("_a"):
            continue

        if short_name.lower() in IGNORE_AUTO_CHAR_TOP_GROUPS:
            continue

        result.append(node)

    return result


def detect_character_prefix():
    """
    Detect CHAR from the CHARACTER top group, not the generic rig root.

    Important example:
        sanjay_a  -> CHAR = "sanjay_a"
        vasu_a    -> CHAR = "vasu_a"
        rig_a     -> NEVER used for CHAR

    Detection order:
        1. Selected top group, when it is a valid *_a character group.
        2. Valid world-level *_a character groups, ignoring rig_a.
        3. Fallback to the hand-control hierarchy only when that root is not rig_a.
    """
    selected_root = selected_top_group()

    # ------------------------------------------------------------------
    # 1. Prefer a valid selected character top group.
    # ------------------------------------------------------------------
    if selected_root:
        selected_name = leaf_name(selected_root)
        selected_short = selected_name.split(":")[-1]

        if (
            selected_short.endswith("_a")
            and selected_short.lower() not in IGNORE_AUTO_CHAR_TOP_GROUPS
        ):
            print("AUTO CHARACTER TOP GROUP: " + selected_name)
            print("AUTO CHAR: " + selected_name)
            return selected_name

    # ------------------------------------------------------------------
    # 2. Find the actual character top group at world level.
    #    This prevents generic rig_a from becoming CHAR.
    # ------------------------------------------------------------------
    world_candidates = scene_character_top_groups()

    if world_candidates:
        root = world_candidates[0]

        if len(world_candidates) > 1:
            cmds.warning(
                "Multiple *_a character top groups found: {}. "
                "Using {}. Select a node under the required character "
                "before running if you need another one.".format(
                    ", ".join(leaf_name(x) for x in world_candidates),
                    leaf_name(root)
                )
            )

        top_group_name = leaf_name(root)
        print("AUTO CHARACTER TOP GROUP: " + top_group_name)
        print("AUTO CHAR: " + top_group_name)
        return top_group_name

    # ------------------------------------------------------------------
    # 3. Fallback: inspect hierarchy containing known hand snap controls,
    #    but explicitly reject generic rig_a.
    # ------------------------------------------------------------------
    hierarchy_candidates = []

    for side in BUILD_SIDES:
        setup = SIDE_SETUP.get(side, {})
        snap_leaf = setup.get("snap")

        if not snap_leaf:
            continue

        for snap_node in find_scene_nodes_by_leaf(snap_leaf):
            root = top_transform(snap_node)

            if not root:
                continue

            root_name = leaf_name(root)
            root_short = root_name.split(":")[-1]

            if root_short.lower() in IGNORE_AUTO_CHAR_TOP_GROUPS:
                continue

            if root_short.endswith("_a") and root not in hierarchy_candidates:
                hierarchy_candidates.append(root)

    if hierarchy_candidates:
        root = hierarchy_candidates[0]
        top_group_name = leaf_name(root)
        print("AUTO CHARACTER TOP GROUP: " + top_group_name)
        print("AUTO CHAR: " + top_group_name)
        return top_group_name

    cmds.error(
        "Could not find a valid character top group ending in '_a'. "
        "The generic group 'rig_a' is intentionally ignored. "
        "Expected a world-level character group such as sanjay_a or vasu_a."
    )


def format_name(template_key, **kwargs):
    """Build a Maya node name from NAME_TEMPLATES."""
    values = {
        "char": CHAR,
        "side": "",
        "finger": "",
        "fk": "",
        "base": "",
        "suffix": "",
    }
    values.update(kwargs)
    return NAME_TEMPLATES[template_key].format(**values)


def hand_ctrl(side):
    return format_name("hand_ctrl", side=side)


def hand_ctrl_group(side):
    return format_name("hand_ctrl_group", side=side)


def meta_ctrl(side, finger):
    return format_name("meta_ctrl", side=side, finger=finger)


def meta_offset(side, finger):
    return format_name("meta_offset", side=side, finger=finger)


def finger_ctrl(side, finger, fk):
    return format_name(
        "finger_ctrl",
        side=side,
        finger=finger,
        fk=fk
    )


def finger_offset(side, finger, fk):
    return format_name(
        "finger_offset",
        side=side,
        finger=finger,
        fk=fk
    )


def thumb_ctrl(side, fk):
    return format_name("thumb_ctrl", side=side, fk=fk)


def thumb_offset(side, fk):
    return format_name("thumb_offset", side=side, fk=fk)


def upper_group(ctrl, suffix):
    """Return the generated upper-group name for a control."""
    base = ctrl[:-4] if ctrl.endswith("_ctl") else ctrl
    return format_name(
        "upper_group",
        base=base,
        suffix=suffix
    )


def normalize_name(name):
    """Remove spaces/underscores and lowercase a name for safe comparison."""
    return name.replace(" ", "").replace("_", "").lower()


def find_existing_attr(ctrl, target_name):
    """
    Find an existing custom attribute by either:
    - Maya long name, for example Spread_Thumb
    - Nice name, for example Spread Thumb
    """
    if not cmds.objExists(ctrl):
        return None

    target_key = normalize_name(target_name)

    for attr in cmds.listAttr(ctrl, userDefined=True) or []:
        plug = "{}.{}".format(ctrl, attr)

        try:
            nice_name = cmds.addAttr(
                plug,
                query=True,
                niceName=True
            ) or attr
        except RuntimeError:
            nice_name = attr

        if (
            normalize_name(attr) == target_key
            or normalize_name(nice_name) == target_key
        ):
            return attr

    return None


def all_hand_controls(side):
    """
    Return controls in the same order as the original group-creation script:
    meta, three FK controls, repeated for four fingers, then three thumb FK.
    """
    controls = []

    for finger in range(4):
        controls.append(meta_ctrl(side, finger))

        for fk in range(3):
            controls.append(finger_ctrl(side, finger, fk))

    for fk in range(3):
        controls.append(thumb_ctrl(side, fk))

    return controls


def original_offset(ctrl, side):
    """Find the original parent/offset node for a hand control."""
    for finger in range(4):
        if ctrl == meta_ctrl(side, finger):
            return meta_offset(side, finger)

        for fk in range(3):
            if ctrl == finger_ctrl(side, finger, fk):
                return finger_offset(side, finger, fk)

    for fk in range(3):
        if ctrl == thumb_ctrl(side, fk):
            return thumb_offset(side, fk)

    return None


def parent_keep_world(node, parent_node):
    """Parent a node without changing its world-space position or rotation."""
    matrix = cmds.xform(
        node,
        query=True,
        worldSpace=True,
        matrix=True
    )

    cmds.parent(
        node,
        parent_node,
        absolute=True
    )

    cmds.xform(
        node,
        worldSpace=True,
        matrix=matrix
    )


def unparent_keep_world(node):
    """Move a transform to world while preserving its world transform."""
    if not cmds.objExists(node):
        return False

    parent = cmds.listRelatives(
        node,
        parent=True,
        fullPath=True
    ) or []

    if not parent:
        return True

    matrix = cmds.xform(
        node,
        query=True,
        worldSpace=True,
        matrix=True
    )

    cmds.parent(node, world=True)

    cmds.xform(
        node,
        worldSpace=True,
        matrix=matrix
    )

    return True


def replace_expression(expression_name, expression_script):
    """Delete an old expression and create its updated replacement."""
    if cmds.objExists(expression_name):
        cmds.delete(expression_name)

    return cmds.expression(
        name=expression_name,
        string=expression_script,
        alwaysEvaluate=True,
        unitConversion="all"
    )


def required_nodes_exist(nodes, label):
    """Check multiple nodes and print warnings for anything missing."""
    valid = True

    for node in nodes:
        if not cmds.objExists(node):
            cmds.warning("{} missing: {}".format(label, node))
            valid = False

    return valid


def direct_connect(driver_plug, target_plug):
    """Safely make a direct Maya attribute connection."""
    if not cmds.objExists(driver_plug):
        cmds.warning("Driver missing: " + driver_plug)
        return False

    if not cmds.objExists(target_plug):
        cmds.warning("Target missing: " + target_plug)
        return False

    cmds.connectAttr(
        driver_plug,
        target_plug,
        force=True
    )
    log("Connected: {} -> {}".format(driver_plug, target_plug))
    return True


def multiply_connect(driver_plug, target_node, target_axis, multiplier, label):
    """
    Connect one driver through a multiplyDivide node.

    Formula:
        target rotation = driver value * multiplier
    """
    target_plug = "{}.{}".format(target_node, target_axis)

    if not cmds.objExists(driver_plug):
        cmds.warning("Driver missing: " + driver_plug)
        return False

    if not cmds.objExists(target_plug):
        cmds.warning("Target missing: " + target_plug)
        return False

    mult_name = "{}_{}_{}_mult".format(
        target_node,
        target_axis,
        label
    )

    if cmds.objExists(mult_name):
        if cmds.nodeType(mult_name) != "multiplyDivide":
            cmds.delete(mult_name)
            mult_name = cmds.createNode(
                "multiplyDivide",
                name=mult_name
            )
    else:
        mult_name = cmds.createNode(
            "multiplyDivide",
            name=mult_name
        )

    cmds.setAttr(mult_name + ".operation", 1)
    cmds.setAttr(mult_name + ".input2X", multiplier)

    cmds.connectAttr(
        driver_plug,
        mult_name + ".input1X",
        force=True
    )

    cmds.connectAttr(
        mult_name + ".outputX",
        target_plug,
        force=True
    )

    log(
        "Connected: {} * {} -> {}".format(
            driver_plug,
            multiplier,
            target_plug
        )
    )
    return True


# =============================================================================
# STEP 01 — CREATE LEFT/RIGHT ATTRIBUTE CONTROLS AND CUSTOM ATTRIBUTES
# =============================================================================

def add_missing_hand_attributes(ctrl):
    """Add only attributes that do not already exist on the control."""
    for attr_name, attr_type in ATTRIBUTES:
        plug = "{}.{}".format(ctrl, attr_name)

        if cmds.objExists(plug):
            continue

        nice_name = attr_name.replace("_", " ")

        if attr_type == "bool":
            cmds.addAttr(
                ctrl,
                longName=attr_name,
                niceName=nice_name,
                attributeType="bool",
                defaultValue=1,
                keyable=True
            )
        else:
            cmds.addAttr(
                ctrl,
                longName=attr_name,
                niceName=nice_name,
                attributeType="double",
                defaultValue=0,
                keyable=True
            )


def format_hand_attribute_control(ctrl):
    """Lock transform channels and format section-header attributes."""
    for attr_name in HEADER_ATTRIBUTES:
        plug = "{}.{}".format(ctrl, attr_name)

        if cmds.objExists(plug):
            cmds.setAttr(plug, lock=False)
            cmds.setAttr(
                plug,
                lock=True,
                keyable=False,
                channelBox=True
            )

    for attr_name in (
        "tx", "ty", "tz",
        "rx", "ry", "rz",
        "sx", "sy", "sz"
    ):
        plug = "{}.{}".format(ctrl, attr_name)

        if cmds.objExists(plug):
            cmds.setAttr(plug, lock=False)
            cmds.setAttr(
                plug,
                lock=True,
                keyable=False,
                channelBox=False
            )

    visibility = ctrl + ".visibility"

    if cmds.objExists(visibility):
        cmds.setAttr(visibility, lock=False)
        cmds.setAttr(
            visibility,
            lock=True,
            keyable=False,
            channelBox=True
        )


def create_hand_attribute_control(side):
    """Create or update one hand attribute control."""
    setup = SIDE_SETUP[side]

    snap = setup["snap"]
    joint = setup["joint"]
    color = setup["color"]

    ctrl = hand_ctrl(side)
    grp = hand_ctrl_group(side)

    if not required_nodes_exist(
        [snap, joint],
        "{} base rig node".format(side)
    ):
        return None

    # Preserve an existing control when requested.
    if cmds.objExists(ctrl) and not REBUILD_ATTRIBUTE_CONTROLS:
        # If the expected group already exists, force it back to WORLD level.
        # This guarantees the attribute-control group is never parented to a joint.
        if cmds.objExists(grp):
            unparent_keep_world(grp)

        add_missing_hand_attributes(ctrl)
        format_hand_attribute_control(ctrl)
        log("Updated existing control: " + ctrl)
        return ctrl

    # Remove the previous control setup before rebuilding it.
    if cmds.objExists(grp):
        cmds.delete(grp)
    elif cmds.objExists(ctrl):
        cmds.delete(ctrl)

    # Create the eight-CV hand attribute control.
    ctrl = cmds.circle(
        name=ctrl,
        normal=(0, 1, 0),
        radius=1,
        degree=3,
        sections=8,
        constructionHistory=False
    )[0]

    # Match the original custom shape edits.
    cmds.move(
        2.461736, 0, 0,
        ctrl + ".cv[3]",
        relative=True,
        objectSpace=True
    )
    cmds.scale(
        1, 1, 2.275455,
        ctrl + ".cv[3]",
        relative=True
    )
    cmds.scale(
        1, 1, 1.887395,
        ctrl + ".cv[2]",
        ctrl + ".cv[4]",
        relative=True
    )
    cmds.move(
        0.0812776, 0, 0,
        ctrl + ".cv[3]",
        relative=True,
        objectSpace=True
    )

    # Mirror only the right-side control shape.
    if side == "R":
        cmds.scale(
            -1, 1, 1,
            ctrl + ".cv[*]",
            relative=True,
            objectSpace=True
        )

    # Match the control to the hand and freeze its transforms.
    cmds.matchTransform(
        ctrl,
        snap,
        position=True,
        rotation=True
    )
    cmds.scale(0.141, 0.141, 0.141, ctrl)
    cmds.makeIdentity(
        ctrl,
        apply=True,
        translate=True,
        rotate=True,
        scale=True,
        normal=False
    )

    # Apply the chosen viewport color.
    for shape in cmds.listRelatives(
        ctrl,
        shapes=True,
        noIntermediate=True,
        fullPath=True
    ) or []:
        cmds.setAttr(shape + ".overrideEnabled", 1)
        cmds.setAttr(shape + ".overrideColor", color)

    add_missing_hand_attributes(ctrl)

    # Create the top group.
    # IMPORTANT: this group intentionally remains at WORLD level.
    # It is never parented under the arm joint.
    grp = cmds.group(
        ctrl,
        name=grp
    )
    unparent_keep_world(grp)

    # Follow the arm-end joint through constraints only.
    # This keeps the control visually attached to the hand while keeping
    # the *_ctl_grp outside the joint hierarchy.
    cmds.parentConstraint(
        joint,
        grp,
        maintainOffset=True
    )
    cmds.scaleConstraint(
        joint,
        grp,
        maintainOffset=True
    )

    format_hand_attribute_control(ctrl)

    log("Created control: " + ctrl)
    return ctrl


def step_01_create_attribute_controls():
    created = []

    for side in BUILD_SIDES:
        result = create_hand_attribute_control(side)

        if result:
            created.append(result)

    if created:
        print("Step 01 complete: {} attribute controls ready.".format(
            len(created)
        ))
    else:
        cmds.warning("Step 01: no hand attribute controls were created.")

    return created


# =============================================================================
# STEP 02 — CREATE THE UPPER-GROUP CHAINS
# =============================================================================

def create_upper_groups_for_control(ctrl, side):
    """
    Insert this group chain above one control:

    Cup1 > Cup2 > Cup3 > Spread_A > Spread_B > Nice_A > Nice_B >
    Scrunch_1 > Scrunch_2 > Fist > Curl > original control
    """
    if not cmds.objExists(ctrl):
        cmds.warning("Control missing: " + ctrl)
        return False

    offset = original_offset(ctrl, side)

    if not offset or not cmds.objExists(offset):
        cmds.warning(
            "Original offset missing for {}: {}".format(ctrl, offset)
        )
        return False

    control_matrix = cmds.xform(
        ctrl,
        query=True,
        worldSpace=True,
        matrix=True
    )

    parent_node = offset

    for suffix in UPPER_GROUP_SUFFIXES:
        grp = upper_group(ctrl, suffix)

        if not cmds.objExists(grp):
            grp = cmds.group(
                empty=True,
                name=grp
            )
            cmds.xform(
                grp,
                worldSpace=True,
                matrix=control_matrix
            )

        current_parent = cmds.listRelatives(
            grp,
            parent=True,
            fullPath=False
        ) or []

        if not current_parent or current_parent[0] != parent_node:
            parent_keep_world(grp, parent_node)

        parent_node = grp

    current_parent = cmds.listRelatives(
        ctrl,
        parent=True,
        fullPath=False
    ) or []

    if not current_parent or current_parent[0] != parent_node:
        parent_keep_world(ctrl, parent_node)

    log("Upper groups ready: " + ctrl)
    return True


def step_02_create_upper_groups():
    completed = 0

    for side in BUILD_SIDES:
        for ctrl in all_hand_controls(side):
            if create_upper_groups_for_control(ctrl, side):
                completed += 1

    print("Step 02 complete: {} controls processed.".format(completed))


# =============================================================================
# STEP 03 — CUP 1
# =============================================================================

def create_cup1(side):
    ctrl = hand_ctrl(side)
    attr = find_existing_attr(ctrl, "Cup 1")

    pinky = upper_group(meta_ctrl(side, 3), "Cup1")
    ring = upper_group(meta_ctrl(side, 2), "Cup1")
    expr_name = ctrl + "_Cup1_expr"

    if not attr:
        cmds.warning("Cup 1 attribute missing: " + ctrl)
        return False

    if not required_nodes_exist([pinky, ring], "Cup 1 target"):
        return False

    script = """
float $v = {ctrl}.{attr};
{pinky}.rotateZ = $v * {pinky_mult};
{ring}.rotateZ = $v * {ring_mult};
""".format(
        ctrl=ctrl,
        attr=attr,
        pinky=pinky,
        ring=ring,
        pinky_mult=CUP1_PINKY_MULTIPLIER,
        ring_mult=CUP1_RING_MULTIPLIER
    )

    replace_expression(expr_name, script)
    log("Cup 1 ready: " + side)
    return True


def step_03_create_cup1():
    for side in BUILD_SIDES:
        create_cup1(side)


# =============================================================================
# STEP 04 — CUP 2
# =============================================================================

def create_cup2(side):
    ctrl = hand_ctrl(side)
    attr = find_existing_attr(ctrl, "Cup 2")
    target = upper_group(meta_ctrl(side, 3), "Cup2")
    expr_name = ctrl + "_Cup2_expr"

    if not attr:
        cmds.warning("Cup 2 attribute missing: " + ctrl)
        return False

    if not cmds.objExists(target):
        cmds.warning("Cup 2 target missing: " + target)
        return False

    script = "{}.rotateZ = {}.{};".format(
        target,
        ctrl,
        attr
    )

    replace_expression(expr_name, script)
    log("Cup 2 ready: " + side)
    return True


def step_04_create_cup2():
    for side in BUILD_SIDES:
        create_cup2(side)


# =============================================================================
# STEP 05 — CUP 3
# =============================================================================

def create_cup3(side):
    ctrl = hand_ctrl(side)
    attr = find_existing_attr(ctrl, "Cup 3")
    target = upper_group(thumb_ctrl(side, 0), "Cup3")
    expr_name = ctrl + "_Cup3_flowExpr"

    if not attr:
        cmds.warning("Cup 3 attribute missing: " + ctrl)
        return False

    if not cmds.objExists(target):
        cmds.warning("Cup 3 target missing: " + target)
        return False

    script = "{}.rotateY = {}.{};".format(
        target,
        ctrl,
        attr
    )

    replace_expression(expr_name, script)
    log("Cup 3 ready: " + side)
    return True


def step_05_create_cup3():
    for side in BUILD_SIDES:
        create_cup3(side)


# =============================================================================
# STEP 06 — FIST
# =============================================================================

def create_fist(side):
    driver = "{}.Fist".format(hand_ctrl(side))

    # Main fingers:
    # Fist 100 creates rotateZ 60 with multiplier 0.60.
    for finger in range(4):
        for fk in range(3):
            target = upper_group(
                finger_ctrl(side, finger, fk),
                "Fist"
            )

            multiply_connect(
                driver,
                target,
                "rotateZ",
                FIST_MAIN_MULTIPLIER,
                "Fist"
            )

    # Thumb FK0 receives two rotations.
    thumb0 = upper_group(thumb_ctrl(side, 0), "Fist")

    multiply_connect(
        driver,
        thumb0,
        "rotateY",
        FIST_THUMB_FK0_Y_MULTIPLIER,
        "Fist"
    )
    multiply_connect(
        driver,
        thumb0,
        "rotateZ",
        FIST_THUMB_FK0_Z_MULTIPLIER,
        "Fist"
    )

    # Thumb FK1 and FK2 rotate on Z.
    multiply_connect(
        driver,
        upper_group(thumb_ctrl(side, 1), "Fist"),
        "rotateZ",
        FIST_THUMB_FK1_Z_MULTIPLIER,
        "Fist"
    )
    multiply_connect(
        driver,
        upper_group(thumb_ctrl(side, 2), "Fist"),
        "rotateZ",
        FIST_THUMB_FK2_Z_MULTIPLIER,
        "Fist"
    )

    log("Fist ready: " + side)


def step_06_create_fist():
    for side in BUILD_SIDES:
        create_fist(side)


# =============================================================================
# STEP 07 — NICE A
# =============================================================================

def create_nice_a(side):
    ctrl = hand_ctrl(side)
    attr = find_existing_attr(ctrl, "Nice A")
    expr_name = ctrl + "_NiceA_verticalSpread_expr"

    if not attr:
        cmds.warning("Nice A attribute missing: " + ctrl)
        return False

    targets = []

    for finger, multiplier in enumerate(NICE_A_MULTIPLIERS):
        targets.append((
            upper_group(meta_ctrl(side, finger), "Nice_A"),
            multiplier
        ))

    if not required_nodes_exist(
        [item[0] for item in targets],
        "Nice A target"
    ):
        return False

    lines = ["float $v = {}.{};".format(ctrl, attr)]

    for target, multiplier in targets:
        lines.append(
            "{}.rotateX = $v * {};".format(
                target,
                multiplier
            )
        )

    replace_expression(expr_name, "\n".join(lines))
    log("Nice A ready: " + side)
    return True


def step_07_create_nice_a():
    for side in BUILD_SIDES:
        create_nice_a(side)


# =============================================================================
# STEP 08 — NICE B
# =============================================================================

def create_nice_b(side):
    ctrl = hand_ctrl(side)
    attr = find_existing_attr(ctrl, "Nice B")
    expr_name = ctrl + "_NiceB_verticalReverseExpr"

    if not attr:
        cmds.warning("Nice B attribute missing: " + ctrl)
        return False

    targets = {}

    for finger in range(4):
        targets[finger] = [
            upper_group(finger_ctrl(side, finger, fk), "Nice_B")
            for fk in range(3)
        ]

    missing = []

    for finger_groups in targets.values():
        for grp in finger_groups:
            if not cmds.objExists(grp):
                missing.append(grp)

    if missing:
        for grp in missing:
            cmds.warning("Nice B target missing: " + grp)
        return False

    lines = [
        "float $v = {}.{};".format(ctrl, attr),
        "if ($v >= 0) {"
    ]

    for finger in (3, 2, 1, 0):
        multiplier = NICE_B_POSITIVE[finger]

        for grp in targets[finger]:
            lines.append(
                "    {}.rotateZ = $v * {};".format(
                    grp,
                    multiplier
                )
            )

    lines.extend([
        "} else {",
        "    float $n = -$v;"
    ])

    for finger in (3, 2, 1, 0):
        multiplier = NICE_B_NEGATIVE[finger]

        for grp in targets[finger]:
            lines.append(
                "    {}.rotateZ = $n * {};".format(
                    grp,
                    multiplier
                )
            )

    lines.append("}")

    replace_expression(expr_name, "\n".join(lines))
    log("Nice B ready: " + side)
    return True


def step_08_create_nice_b():
    for side in BUILD_SIDES:
        create_nice_b(side)


# =============================================================================
# STEP 09 — SCRUNCH 1
# =============================================================================

def create_scrunch1(side):
    ctrl = hand_ctrl(side)
    attr = find_existing_attr(ctrl, "Scrunch 1")
    expr_name = ctrl + "_Scrunch1_expr"

    if not attr:
        cmds.warning("Scrunch 1 attribute missing: " + ctrl)
        return False

    lines = ["float $v = {}.{};".format(ctrl, attr)]
    valid_targets = 0

    # First FK section: all fingers use -0.50.
    for finger in range(4):
        target = upper_group(
            finger_ctrl(side, finger, 0),
            "Scrunch_1"
        )

        if cmds.objExists(target):
            lines.append(
                "{}.rotateZ = $v * {};".format(
                    target,
                    SCRUNCH1_FK0_MULTIPLIER
                )
            )
            valid_targets += 1
        else:
            cmds.warning("Scrunch 1 target missing: " + target)

    # Second FK section: each finger has a separate multiplier.
    for finger, multiplier in enumerate(SCRUNCH1_FK1_MULTIPLIERS):
        target = upper_group(
            finger_ctrl(side, finger, 1),
            "Scrunch_1"
        )

        if cmds.objExists(target):
            lines.append(
                "{}.rotateZ = $v * {};".format(
                    target,
                    multiplier
                )
            )
            valid_targets += 1
        else:
            cmds.warning("Scrunch 1 target missing: " + target)

    # Third FK section: all fingers use 0.50.
    for finger in range(4):
        target = upper_group(
            finger_ctrl(side, finger, 2),
            "Scrunch_1"
        )

        if cmds.objExists(target):
            lines.append(
                "{}.rotateZ = $v * {};".format(
                    target,
                    SCRUNCH1_FK2_MULTIPLIER
                )
            )
            valid_targets += 1
        else:
            cmds.warning("Scrunch 1 target missing: " + target)

    if not valid_targets:
        return False

    replace_expression(expr_name, "\n".join(lines))
    log("Scrunch 1 ready: " + side)
    return True


def step_09_create_scrunch1():
    for side in BUILD_SIDES:
        create_scrunch1(side)


# =============================================================================
# STEP 10 — SCRUNCH 2
# =============================================================================

def create_scrunch2(side):
    ctrl = hand_ctrl(side)
    attr = find_existing_attr(ctrl, "Scrunch 2")
    expr_name = ctrl + "_Scrunch2_groupExpr"

    if not attr:
        cmds.warning("Scrunch 2 attribute missing: " + ctrl)
        return False

    lines = ["float $v = {}.{};".format(ctrl, attr)]
    valid_targets = 0

    for fk in (0, 1, 2):
        multiplier = SCRUNCH2_FK_MULTIPLIERS[fk]

        for finger in range(4):
            target = upper_group(
                finger_ctrl(side, finger, fk),
                "Scrunch_2"
            )

            if cmds.objExists(target):
                lines.append(
                    "{}.rotateZ = $v * {};".format(
                        target,
                        multiplier
                    )
                )
                valid_targets += 1
            else:
                cmds.warning("Scrunch 2 target missing: " + target)

    if not valid_targets:
        return False

    replace_expression(expr_name, "\n".join(lines))
    log("Scrunch 2 ready: " + side)
    return True


def step_10_create_scrunch2():
    for side in BUILD_SIDES:
        create_scrunch2(side)


# =============================================================================
# STEP 11 — SPREAD A
# =============================================================================

def create_spread_a(side):
    ctrl = hand_ctrl(side)
    spread_attr = find_existing_attr(ctrl, "Spread A")

    # Pinky Cup is optional. It is not created in Step 1.
    # When it does not exist, Spread A uses a fixed ratio of 1.0.
    pinky_cup_attr = find_existing_attr(ctrl, "Pinky Cup")

    expr_name = ctrl + "_SpreadA_ratio_expr"

    index_target = upper_group(meta_ctrl(side, 0), "Spread_A")
    ring_target = upper_group(meta_ctrl(side, 2), "Spread_A")
    pinky_target = upper_group(meta_ctrl(side, 3), "Spread_A")

    if not spread_attr:
        cmds.warning("Spread A attribute missing: " + ctrl)
        return False

    if not required_nodes_exist(
        [index_target, ring_target, pinky_target],
        "Spread A target"
    ):
        return False

    if pinky_cup_attr:
        pinky_ratio = "{}.{} / 100.0".format(
            ctrl,
            pinky_cup_attr
        )
    else:
        pinky_ratio = "1.0"

    script = """
float $sp = {ctrl}.{spread};
float $pc = {pinky_ratio};

{index}.rotateY = $sp;
{pinky}.rotateY = -($sp * $pc);
{ring}.rotateY = -($sp * $pc * {ring_mult});
""".format(
        ctrl=ctrl,
        spread=spread_attr,
        pinky_ratio=pinky_ratio,
        index=index_target,
        pinky=pinky_target,
        ring=ring_target,
        ring_mult=SPREAD_RING_MULTIPLIER
    )

    replace_expression(expr_name, script)
    log("Spread A ready: " + side)
    return True


def step_11_create_spread_a():
    for side in BUILD_SIDES:
        create_spread_a(side)


# =============================================================================
# STEP 12 — SPREAD B
# =============================================================================

def create_spread_b(side):
    ctrl = hand_ctrl(side)
    attr = find_existing_attr(ctrl, "Spread B")
    expr_name = ctrl + "_SpreadB_expr"

    index_target = upper_group(
        finger_ctrl(side, 0, 0),
        "Spread_B"
    )
    ring_target = upper_group(
        finger_ctrl(side, 2, 0),
        "Spread_B"
    )
    pinky_target = upper_group(
        finger_ctrl(side, 3, 0),
        "Spread_B"
    )

    if not attr:
        cmds.warning("Spread B attribute missing: " + ctrl)
        return False

    if not required_nodes_exist(
        [index_target, ring_target, pinky_target],
        "Spread B target"
    ):
        return False

    script = """
float $sp = {ctrl}.{attr};

{index}.rotateY = $sp;
{pinky}.rotateY = -$sp;
{ring}.rotateY = -($sp * {ring_mult});
""".format(
        ctrl=ctrl,
        attr=attr,
        index=index_target,
        pinky=pinky_target,
        ring=ring_target,
        ring_mult=SPREAD_RING_MULTIPLIER
    )

    replace_expression(expr_name, script)
    log("Spread B ready: " + side)
    return True


def step_12_create_spread_b():
    for side in BUILD_SIDES:
        create_spread_b(side)


# =============================================================================
# STEP 13 — SPREAD THUMB
# =============================================================================

def create_spread_thumb(side):
    ctrl = hand_ctrl(side)
    attr = find_existing_attr(ctrl, "Spread Thumb")
    expr_name = ctrl + "_SpreadThumb_expr"

    # This intentionally uses the thumb's Spread_A upper group.
    # Your original Step 2 did not create a separate Spread_Thumb group.
    target = upper_group(
        thumb_ctrl(side, 0),
        "Spread_A"
    )

    if not attr:
        cmds.warning("Spread Thumb attribute missing: " + ctrl)
        return False

    if not cmds.objExists(target):
        cmds.warning("Spread Thumb target missing: " + target)
        return False

    script = "{}.rotateZ = {}.{};".format(
        target,
        ctrl,
        attr
    )

    replace_expression(expr_name, script)
    log("Spread Thumb ready: " + side)
    return True


def step_13_create_spread_thumb():
    for side in BUILD_SIDES:
        create_spread_thumb(side)


# =============================================================================
# STEP 14 — INDIVIDUAL FINGER AND THUMB CURL CONNECTIONS
# =============================================================================

def curl_connection_data(side):
    """
    Build the individual Curl mapping.

    Meta Curl 0 attributes rotate the meta groups on X.
    Finger/Thumb Curl attributes rotate their Curl groups on Z.
    """
    finger_names = (
        "Index",
        "Middle",
        "Ring",
        "Pinky",
    )

    data = []

    for finger, finger_name in enumerate(finger_names):
        data.append((
            "{} Curl 0".format(finger_name),
            upper_group(meta_ctrl(side, finger), "Curl"),
            "rotateX"
        ))

        for curl_index in (1, 2, 3):
            fk = curl_index - 1

            data.append((
                "{} Curl {}".format(finger_name, curl_index),
                upper_group(
                    finger_ctrl(side, finger, fk),
                    "Curl"
                ),
                "rotateZ"
            ))

    for curl_index in (0, 1, 2):
        data.append((
            "Thumb Curl {}".format(curl_index),
            upper_group(
                thumb_ctrl(side, curl_index),
                "Curl"
            ),
            "rotateZ"
        ))

    return data


def create_individual_curls(side):
    ctrl = hand_ctrl(side)

    if not cmds.objExists(ctrl):
        cmds.warning("Curl control missing: " + ctrl)
        return False

    connected = 0

    for nice_name, target, axis in curl_connection_data(side):
        attr = find_existing_attr(ctrl, nice_name)

        if not attr:
            cmds.warning(
                "Curl attribute missing on {}: {}".format(
                    ctrl,
                    nice_name
                )
            )
            continue

        driver_plug = "{}.{}".format(ctrl, attr)
        target_plug = "{}.{}".format(target, axis)

        if direct_connect(driver_plug, target_plug):
            connected += 1

    print(
        "{} hand Curl connections: {}/19".format(
            side,
            connected
        )
    )
    return connected > 0


def step_14_create_individual_curls():
    for side in BUILD_SIDES:
        create_individual_curls(side)


# =============================================================================
# F. MASTER BUILD FUNCTION — RUNS STEPS 1 TO 14 IN NUMBER ORDER
# =============================================================================

STEP_FUNCTIONS = {
    1: ("Create attribute controls", step_01_create_attribute_controls),
    2: ("Create upper groups", step_02_create_upper_groups),
    3: ("Connect Cup 1", step_03_create_cup1),
    4: ("Connect Cup 2", step_04_create_cup2),
    5: ("Connect Cup 3", step_05_create_cup3),
    6: ("Connect Fist", step_06_create_fist),
    7: ("Connect Nice A", step_07_create_nice_a),
    8: ("Connect Nice B", step_08_create_nice_b),
    9: ("Connect Scrunch 1", step_09_create_scrunch1),
    10: ("Connect Scrunch 2", step_10_create_scrunch2),
    11: ("Connect Spread A", step_11_create_spread_a),
    12: ("Connect Spread B", step_12_create_spread_b),
    13: ("Connect Spread Thumb", step_13_create_spread_thumb),
    14: ("Connect individual Curls", step_14_create_individual_curls),
}


def validate_settings():
    """Catch simple configuration mistakes before changing the Maya scene."""
    for side in BUILD_SIDES:
        if side not in ("L", "R"):
            cmds.error(
                "BUILD_SIDES supports only 'L' and 'R'. Invalid side: {}".format(
                    side
                )
            )

        if side not in SIDE_SETUP:
            cmds.error("SIDE_SETUP is missing side: " + side)

        for required_key in ("snap", "joint", "color"):
            if required_key not in SIDE_SETUP[side]:
                cmds.error(
                    "SIDE_SETUP[{}] is missing key: {}".format(
                        side,
                        required_key
                    )
                )

    invalid_steps = [
        step for step in RUN_STEPS
        if step not in STEP_FUNCTIONS
    ]

    if invalid_steps:
        cmds.error(
            "Invalid RUN_STEPS values: {}".format(invalid_steps)
        )


def build_hand_attribute_system():
    """Build the complete left/right hand attribute system."""
    global CHAR

    validate_settings()

    # Automatically use the character rig's highest/top group name.
    CHAR = detect_character_prefix()

    selected_steps = sorted(set(RUN_STEPS))
    completed_steps = []

    cmds.undoInfo(openChunk=True)

    try:
        print("\n" + "#" * 72)
        print("BUILDING HAND ATTRIBUTE SYSTEM FOR: " + CHAR)
        print("SIDES: " + ", ".join(BUILD_SIDES))
        print("STEPS: " + ", ".join(str(x) for x in selected_steps))
        print("#" * 72)

        for step_number in selected_steps:
            title, function = STEP_FUNCTIONS[step_number]

            print_step(step_number, title)
            function()
            completed_steps.append(step_number)

        if SELECT_FINISHED_CONTROLS:
            controls = [
                hand_ctrl(side)
                for side in BUILD_SIDES
                if cmds.objExists(hand_ctrl(side))
            ]

            if controls:
                cmds.select(controls, replace=True)

        print("\n" + "#" * 72)
        print("HAND ATTRIBUTE BUILD COMPLETED")
        print("CHARACTER: " + CHAR)
        print("COMPLETED STEPS: " + ", ".join(
            str(x) for x in completed_steps
        ))
        print("#" * 72)

    except Exception as error:
        cmds.warning(
            "Hand attribute build stopped: {}".format(error)
        )
        raise

    finally:
        cmds.undoInfo(closeChunk=True)


# =============================================================================
# G. RUN THE BUILDER
# =============================================================================
#
# Leave this line active when running the file directly in Maya.
# Comment it out when importing this file as a Python module.
#
build_hand_attribute_system()
cmds.parent("*_Hand_Attribute_*_ctl_grp", "rigging")