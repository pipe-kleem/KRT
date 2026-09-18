"""Shared imports/constants/helpers for the graph package (auto-split from graph.py)."""
import maya.cmds as cmds
import os
import json
import re
import uuid
import copy
import traceback
from ..compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6
from ..utils import apply_control_shapes_library

# ---------------------------------------------------------------------------
# mGear Shifter component discovery
#
# The Module Graph Editor no longer reads custom per-studio .py "module"
# scripts from a hardcoded network path. Instead it lists every real Shifter
# component (classic + epic) the same way Shifter's own Guide Manager does,
# and drives the real mgear guide/build API directly.
# ---------------------------------------------------------------------------

# Sentinel module_type for a node representing mGear's "Rig Plebe" biped
# template workflow (import biped guide -> align to a character-generator
# template) rather than a single atomic Shifter component.
PLEBE_MODULE_TYPE = "__plebe_biped__"
PLEBE_SEARCH_LABEL = "★ mGear Plebe - Biped Template..."

# Sentinel module_type for a node that imports a standalone .sgt guide
# template file the user saved themselves (e.g. a stock component they
# hand-tweaked and re-exported from mGear's own Guide Manager) rather than
# building one of the catalog components listed by list_mgear_components().
CUSTOM_SGT_MODULE_TYPE = "__custom_sgt__"
CUSTOM_SGT_SEARCH_LABEL = "📄 Custom Module (from .sgt file)..."

# Stage 26: sentinel module_type for a node that imports/draws NO guide at
# all - unlike every other node type, it has no catalog component and no
# .sgt file, nothing to configure except its own custom script (the generic
# custom_script_code/lang/when fields every RigNode already has - see
# CustomScriptDialog). Exists purely so a script-only build step (scene
# cleanup, an export, calling into another tool, enforcing build order
# between two unrelated branches, etc) can sit in the graph as its own node
# instead of being tacked onto some unrelated component that happens to be
# nearby. See RigNode.custom_script_ran / ModuleGraphWidget.
# _build_custom_script_node for how it participates in Build Guides/Build
# Modules without ever having a maya_guide_root.
CUSTOM_SCRIPT_MODULE_TYPE = "__custom_script__"
CUSTOM_SCRIPT_SEARCH_LABEL = "📝 Custom Script Module (no guide)..."

# Shared control-shapes library: a .ma/.mb file of "*_controlBuffer" curves
# (mGear's own hand-authored-shape convention - see build_node_guide()) that
# gets merged into every guide's controllers_org automatically, so every
# module's controls come out shaped like this instead of the component's
# generic default icon. Editable per-graph in the Node tab; this is only
# the starting default shown there.
DEFAULT_CONTROL_SHAPES_LIBRARY = r"R:\Pipeline_Share\Pipeline_share\RigUtils\controlShapes.ma"

# Stage 19: the studio's Fan Joint / Stretchy Joint setup scripts for a Plebe
# biped node (Node tab, right after Align Guides Automatically). Both run
# automatically right after this node's rig is actually built ("modules"),
# same timing as the per-node custom script, since they act on real built
# joints rather than guides. Editable per-node in the Node tab (a plain
# python/mel-style text box, same idea as the custom script editor) - these
# are only the starting defaults.
DEFAULT_FAN_JOINT_SCRIPT = (
    "import maya.cmds as cmds\n"
    "import re\n"
    "import sys\n"
    "import importlib\n"
    "import os\n"
    "sys.path.append(r\"R:/Pipeline_Share/Pipeline_share/RigUtils\")\n"
    "import UniUtils\n"
    "importlib.reload(UniUtils)\n"
    "UniUtils.run_Fan()\n"
)
DEFAULT_STRETCHY_JOINT_SCRIPT = (
    "import maya.cmds as cmds\n"
    "import re\n"
    "import sys\n"
    "import importlib\n"
    "import os\n"
    "sys.path.append(r\"R:/Pipeline_Share/Pipeline_share/RigUtils\")\n"
    "import UniUtils\n"
    "importlib.reload(UniUtils)\n"
    "UniUtils.run_stretchy()\n"
)

__all__ = ['CUSTOM_SCRIPT_MODULE_TYPE', 'CUSTOM_SCRIPT_SEARCH_LABEL', 'CUSTOM_SGT_MODULE_TYPE', 'CUSTOM_SGT_SEARCH_LABEL', 'DEFAULT_CONTROL_SHAPES_LIBRARY', 'DEFAULT_FAN_JOINT_SCRIPT', 'DEFAULT_STRETCHY_JOINT_SCRIPT', 'IS_PYSIDE6', 'PLEBE_MODULE_TYPE', 'PLEBE_SEARCH_LABEL', 'QtCore', 'QtGui', 'QtWidgets', 'apply_control_shapes_library', 'cmds', 'copy', 'json', 'os', 're', 'traceback', 'uuid']
