"""Shared imports/constants/helpers for the dialogs package (auto-split from dialogs.py)."""
import maya.cmds as cmds
import os
import re
import uuid
import time
import json
import shutil
import traceback
from ..compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6



# ══════════════════════════════════════════════════════════════════════
# AYON publish — helpers shared by the dialog
# ══════════════════════════════════════════════════════════════════════
_PATH_EXT_RE = re.compile(r"^\.[A-Za-z0-9]{1,8}$")

__all__ = ['IS_PYSIDE6', 'QtCore', 'QtGui', 'QtWidgets', '_PATH_EXT_RE', 'cmds', 'json', 'os', 're', 'shutil', 'time', 'traceback', 'uuid']
