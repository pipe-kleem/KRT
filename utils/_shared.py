"""Shared imports/constants/helpers for the utils package (auto-split from utils.py)."""
import maya.cmds as cmds
import maya.OpenMaya as om
import os
import json
import pickle
import re
import time
import traceback
import gc


# ---------------------------------------------------------------------------
# Material / Shader export-import (KRT "Material" panel)
# ---------------------------------------------------------------------------
# Mirrors export_control_shapes/import_control_shapes above in shape and
# intent, but captures a mesh's assigned shading network instead of curve
# shapes: the shading engine(s) it's a member of (whole-object AND per-face
# assignment), every upstream node in that network (surface/displacement
# shaders, file textures, utility/ramp/layer nodes, place2dTexture, etc -
# any renderer, since none of this is renderer-specific), each node's
# writable attribute values (which is how ANY texture path - fileTextureName
# or a renderer-specific equivalent - gets captured, generically, wherever
# on disk it points), and every connection between those nodes. Texture
# paths are recorded exactly as-is (not copied anywhere) - reloading simply
# reconnects to whatever path was saved, same as the source scene had.

# Attributes that are pure Maya-internal bookkeeping (not shading data at
# all) and can differ or simply not exist between Maya versions/sessions -
# capturing them is pointless and, for cbId in particular, just produces a
# noisy "no attribute" warning on import for no benefit.
_NON_DATA_ATTRS = {"cbId"}


######################################
# SkinCluster helpers (KRT-owned, cmds-only - no PyMEL dependency)
#
# These back the skinCluster panel's "always add missing influences on
# import" and "own canonical skinCluster name" behavior. Everything here
# finds a mesh's skinCluster by walking its construction HISTORY, never by
# a stored/expected name, so it stays correct even after a user manually
# renames a skinCluster in the Outliner - exactly the case that used to
# desync KRT's naming from the scene.
######################################

SKINCLUSTER_SUFFIX = "_SkinCluster"

######################################################################
# Fast SkinCluster save/import (performance)
######################################################################
# mgear.core.skin's exportSkin()/importSkin() are what actually run
# behind KRT's SkinCluster (JSON) and Tweaker panels' "Save Skin" /
# skin-file import. Both already read/write the WHOLE weight buffer in
# a single bulk OpenMaya call (getWeights/setWeights), so that part was
# never the slow part. The slow part is the plain Python loop on either
# side of that buffer that walks EVERY vertex for EVERY influence to
# build (export) or apply (import) the per-influence weight dict, even
# though the file format itself only stores non-zero weights. For a
# mesh with, say, 40k vertices and 80 influences that's ~3.2 million
# individual Python-level dict lookups / MDoubleArray.set() calls -
# each one carrying real interpreter + SWIG-call overhead - which is
# what actually makes Save/Import Skin slow on heavy meshes. On export,
# mgear also always writes the JSON pretty-printed and key-sorted
# (`indent=4, sort_keys=True`), which forces Python's pure-Python JSON
# encoder instead of the C-accelerated one for a large nested dict like
# a dense weights export - a second, separate slowdown on top of the
# loop.
#
# fast_export_skin()/fast_import_skin() below are drop-in replacements
# for mgear.core.skin.exportSkin()/importSkin() that KRT's Save Skin /
# skin-import call sites now use instead. They produce/consume the
# EXACT same .jSkin/.gSkin schema - a file saved here opens fine in
# vanilla mgear, and a file saved by vanilla mgear (or an older KRT
# session) imports fine here - only the hot per-vertex loop and the
# JSON formatting are different:
#   - When numpy is importable (it ships with Maya's own Python since
#     2022) the whole per-influence sparse extraction/scatter is done
#     with vectorized numpy calls instead of a Python-level loop.
#   - Without numpy, a still-meaningfully-faster pure-Python path is
#     used: it converts the OpenMaya weight buffer to a plain list ONCE
#     (avoiding repeated SWIG-wrapped indexing) and, on import, zeroes
#     each replaced influence's column with a single slice assignment
#     instead of one MDoubleArray.set() call per vertex.
# Everything else - skinCluster lookup/creation, blend weights,
# skinningMethod/normalizeWeights attributes, and (on import) any
# vertex-count MISMATCH - is delegated straight to mgear.core.skin,
# completely unchanged, so every edge case mgear already handles keeps
# working exactly as before. If anything in the fast path raises for
# any reason, both functions fall back to calling mgear.core.skin's own
# exportSkin()/importSkin(), so a bug here can only make a save/import
# slower, never break it.
#
# NOT tested live in Maya (this sandbox cannot run Maya) - verified via
# py_compile, an AST duplicate-method scan, and stub tests that replay
# this exact logic against hand-built stand-ins for the OpenMaya calls.
# Please try it on a real heavy mesh before relying on it, and report
# back if Save/Import Skin still feels slow or anything looks off.
try:
    import numpy as _np
except Exception:
    _np = None

__all__ = ['SKINCLUSTER_SUFFIX', '_NON_DATA_ATTRS', '_np', 'cmds', 'gc', 'json', 'om', 'os', 'pickle', 're', 'time', 'traceback']
