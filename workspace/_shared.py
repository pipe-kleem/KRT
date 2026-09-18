"""Shared imports/constants/helpers for the workspace package (auto-split from workspace.py)."""
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as om
import os
import json
import time
import math
import traceback
import re
import shutil
import subprocess
import fnmatch
import tempfile
import getpass
import sys
from ..compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6, QMediaPlayer, QVideoWidget, QAudioOutput, QMediaContent, HAS_MULTIMEDIA
from ..dialogs import AdvancedSaveDialog, BuildProgressDialog, SimpleCodeEditorDialog
from ..widgets import DragDropContainer, SortablePanel, SortableBubblePanel, LodLoaderPanel, panel_run_label, prompt_skincluster_naming_check, PBCameraViewWidget, PBWipeCompareWidget
from ..graph import ModuleGraphWidget, RigNode, RigWire
from ..utils import read_skin_file_meshes, log_crash

# Stage 17: default location for the Rigging Workspace's script/tools
# library - always this by default, but editable per-user (see
# SessionWorkspace.page_scripts / set_scripts_lib_path); a change is saved
# into that user's own session_data.json, same as every other per-user KRT
# preference (recent files, autosave toggle, etc).
DEFAULT_SCRIPTS_LIB_PATH = r"P:\pipeline_database\Maya\Scripts\ONE"

# Stage 37: the studio's shared Studio Library install - KRT's Playblast
# tab reuses Studio Library's own "mutils" package to load a .anim clip
# (see SessionWorkspace.pb_ensure_studiolibrary), instead of re-implementing
# animation-curve pasting from scratch.
DEFAULT_STUDIOLIBRARY_SRC_PATH = r"P:\rigging_team\Rigging_local_share\QC\studiolibrary-2.20.2\src"

# Stage 19: shared look for a labelled section box within a tab (Rigging
# Workspace's Script Library / LOD Build Manager sections) - one place to
# keep this consistent instead of retyping the stylesheet per group box.
SECTION_GROUPBOX_STYLE = (
    "QGroupBox { border: 1px solid #3e3e42; border-radius: 4px; margin-top: 8px; "
    "font-weight: bold; color: #aaa; } "
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")

__all__ = ['AdvancedSaveDialog', 'BuildProgressDialog', 'DEFAULT_SCRIPTS_LIB_PATH', 'DEFAULT_STUDIOLIBRARY_SRC_PATH', 'DragDropContainer', 'HAS_MULTIMEDIA', 'IS_PYSIDE6', 'LodLoaderPanel', 'ModuleGraphWidget', 'PBCameraViewWidget', 'PBWipeCompareWidget', 'QAudioOutput', 'QMediaContent', 'QMediaPlayer', 'QVideoWidget', 'QtCore', 'QtGui', 'QtWidgets', 'RigNode', 'RigWire', 'SECTION_GROUPBOX_STYLE', 'SimpleCodeEditorDialog', 'SortableBubblePanel', 'SortablePanel', 'cmds', 'fnmatch', 'getpass', 'json', 'log_crash', 'math', 'mel', 'om', 'os', 'panel_run_label', 'prompt_skincluster_naming_check', 're', 'read_skin_file_meshes', 'shutil', 'subprocess', 'sys', 'tempfile', 'time', 'traceback']
