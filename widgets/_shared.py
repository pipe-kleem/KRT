"""Shared imports/constants/helpers for the widgets package (auto-split from widgets.py)."""
import maya.cmds as cmds
import maya.OpenMaya as om
import os
import shutil
import subprocess
import json
import time
import re
import uuid
import traceback
from ..compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6
from ..utils import (
    export_control_shapes, import_control_shapes, get_versioned_path,
    find_mismatched_skinclusters, rename_mismatched_skinclusters, log_crash,
    export_material_data, import_material_data,
)
from ..dialogs import BuildProgressDialog

# Per-type accent colours so each panel is visually identifiable at a glance.
# Applied as a coloured left border stripe and the title text colour.
# Stage 18: MA and IMPORT_3D are now ONE panel type (IMPORT_3D auto-detects
# the file's actual format on import - see SessionWorkspace.import_3d_logic
# and SortablePanel.execute) - there is no separate "MA" entry anymore.
PANEL_TYPE_ACCENTS = {
    "SCRIPT":        "#4fc3f7",   # light blue  - Python / MEL scripts (KRT-scoped)
    "GLOBAL_SCRIPT": "#9575cd",   # violet      - Python / MEL scripts (Maya-global, Stage 17)
    "IMPORT_3D":     "#ba68c8",   # purple      - imported 3D models (.ma/.mb/.fbx/.obj/.abc)
    "JSON":          "#81c784",   # green       - skin clusters
    "SHAPES":        "#f06292",   # pink        - control shapes
    "PUBLISH":       "#e57373",   # red         - publish path
    "MODULE":        "#2bb5a8",   # teal        - module bubble panels
    "TWEAKER":       "#4dd0e1",   # cyan        - tweaker setups
    "LOD_LOADER":    "#ffca28",   # amber/gold  - LOD Loader (build entire LODs), Stage 20
    "MATERIAL":      "#ff8a65",   # deep orange - shader/material + texture save-load
    "NOTE":          "#ffd54f",   # yellow      - sticky-note style, for a plain reminder panel
    "IMPORT_LOD":    "#9ccc65",   # light green - Import 3D Model + organize into LOD groups
    "DELETE_OBJ":    "#e53935",   # strong red  - deletes named object(s), deliberately alarming
    "ZERO_OUT":      "#64b5f6",   # sky blue    - resets named object(s)/control(s) to default
    "PARENT_OBJ":    "#ffa726",   # orange      - parents child object(s) under a parent
    "INSTANCE_OBJ":  "#ab47bc",   # purple      - creates preset-transform instances of an object
}

# Stage 17, request "different design per panel type", REVISED Stage 18
# (request "icons should be relatable to that panel, not random"): a small
# icon per type so panels are tellable apart at a glance without reading the
# title text. Each icon is picked to actually depict what that panel does:
# a snake for Python/MEL, a globe for "runs in Maya's global session", a
# cube for a 3D model import, a bone for a skinCluster/bind, a palette for
# control-shape curves, an outbox tray for "send this out" (publish), a
# puzzle piece for a module, and a level slider for "tweak" (weight nudging).
PANEL_TYPE_ICONS = {
    "SCRIPT":        "🐍",
    "GLOBAL_SCRIPT": "🌐",
    "IMPORT_3D":     "🧊",
    "JSON":          "🦴",
    "SHAPES":        "🎨",
    "PUBLISH":       "📤",
    "MODULE":        "🧩",
    "TWEAKER":       "🎚️",
    # Stage 20: LOD Loader builds an entire LOD's whole panel stack, so it
    # gets a "construction/assembly" icon distinct from every single-step type.
    "LOD_LOADER":    "🏗️",
    # Material panel: a paint bucket for "fills a mesh with its saved
    # shader/texture setup" - distinct from SHAPES' palette (that's curve
    # shapes, this is shading).
    "MATERIAL":      "🪣",
    # Note panel: a sticky note, for a plain free-text reminder - it isn't
    # a build step at all (see panel_run_label/SortablePanel.execute).
    "NOTE":          "🗒️",
    # Import 3D + LOD Organize: same cube as IMPORT_3D plus a building -
    # imports, then organizes the scene into LOD groups.
    "IMPORT_LOD":    "🏢",
    # Delete-by-name: a plain trash can - deliberately unambiguous.
    "DELETE_OBJ":    "🗑️",
    # Zero Out: a target/reset symbol for "back to default".
    "ZERO_OUT":      "🎯",
    # Parent: a link, for "attaches one thing under another".
    "PARENT_OBJ":    "🔗",
    # Instance Object: a cloning/duplication symbol - creates preset-
    # transform instances of a named object (see panel UI/execute below).
    "INSTANCE_OBJ":  "🧬",
}

# Stage 17: each panel type's DEFAULT background - a faint wash of its own
# accent colour blended into the old uniform #252526, instead of every panel
# type looking identical apart from the thin border stripe. Precomputed
# (base*0.84 + accent*0.16) rather than blended at runtime, to keep panel
# construction simple. A panel the user has manually recoloured (right-click
# -> Change Panel Color) keeps that choice - this is only ever the STARTING
# color for a newly created panel.
PANEL_TYPE_BG_TINT = {
    "SCRIPT":        "#2c3e47",
    "GLOBAL_SCRIPT": "#332e47",
    "IMPORT_3D":     "#3d3040",
    "JSON":          "#343f35",
    "SHAPES":        "#452f37",
    "PUBLISH":       "#443132",
    "MODULE":        "#263c3b",
    "TWEAKER":       "#2b4044",
    "LOD_LOADER":    "#463d20",
    "MATERIAL":      "#452f28",
    "NOTE":          "#252526",
    "IMPORT_LOD":    "#334a2c",
    "DELETE_OBJ":    "#452a29",
    "ZERO_OUT":      "#2a3c47",
    "PARENT_OBJ":    "#453b28",
    "INSTANCE_OBJ":  "#3a2f45",
}

# Stage 17, "these fields are where we're loading/saving a path, not typing
# one": the panel's main path field is made read-only for the types where
# the field is ALWAYS set by a button/menu action - Browse, Save Skin/
# Shapes, Switch Version - and never by hand. SCRIPT/GLOBAL_SCRIPT are
# excluded on purpose: that field can hold raw pasted code instead of a
# path. Stage 18 adds IMPORT_3D (now that MA/IMPORT_3D are one merged,
# always-Browse-set panel type - request #1).
READONLY_FIELD_TYPES = {"JSON", "SHAPES", "PUBLISH", "TWEAKER", "IMPORT_3D", "MATERIAL", "IMPORT_LOD"}

# Stage 18, request #4: every read-only field across the Rig Workspace uses
# this SAME colour, regardless of which panel type it belongs to - a single
# consistent "this is locked, set automatically" signal instead of Stage
# 17's per-type accent colouring (which made JSON's field green, SHAPES'
# pink, etc. - readable, but not "the same" the way the user asked for).
READONLY_FIELD_COLOR = "#a1887f"   # warm brown

__all__ = ['BuildProgressDialog', 'IS_PYSIDE6', 'PANEL_TYPE_ACCENTS', 'PANEL_TYPE_BG_TINT', 'PANEL_TYPE_ICONS', 'QtCore', 'QtGui', 'QtWidgets', 'READONLY_FIELD_COLOR', 'READONLY_FIELD_TYPES', 'cmds', 'export_control_shapes', 'export_material_data', 'find_mismatched_skinclusters', 'get_versioned_path', 'import_control_shapes', 'import_material_data', 'json', 'log_crash', 'om', 'os', 're', 'rename_mismatched_skinclusters', 'shutil', 'subprocess', 'time', 'traceback', 'uuid']
