"""Shared pieces of the CC Refiner: style sheet, MEL scripts, small Qt helpers."""
import importlib
import json
import math
import os
import re
import sys
import time
from .state import cmds, guard
import maya.api.OpenMaya as om2
import maya.OpenMaya as om1
import maya.OpenMayaUI as omui
from .state import QtCore, QtGui, QtWidgets, wrapInstance

# --- shared third-party imports (UniUtils is imported read-only from the P: share) ---
import re
import maya.mel as mel
import maya.api.OpenMaya as om
try:
    import numpy as np
except ImportError:
    np = None

if r"P:/rigging_team/Pipeline_share/RigUtils" not in sys.path:
    sys.path.append(r"P:/rigging_team/Pipeline_share/RigUtils")   # read only: UniUtils is imported from here
try:
    import UniUtils
    importlib.reload(UniUtils)
except ImportError:
    UniUtils = None
    cmds.warning("wrapMarker: UniUtils not found on P: - Load Ref / BlendShape buttons will not work.")


STYLE = """
QWidget { background: #262729; color: #c9cdd1; font-size: 9pt; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #262729; border: none; }
QLabel { background: transparent; }
QLabel#muted { color: #9aa0a6; }
QLabel#status { background: #1b1c1e; color: #9aa0a6; padding: 6px 10px; border-top: 1px solid #343638; }
QLineEdit, QSpinBox { min-width: 0px; background: #1d1e20; color: #e8eaed; border: 1px solid #3a3d40;
                      border-radius: 4px; padding: 3px 6px;
                      selection-background-color: #3d7fd9; selection-color: #ffffff; }
QLineEdit:focus, QSpinBox:focus { border: 1px solid #5b9cf0; }
QPushButton { background: #3a3d40; color: #e1e4e8; border: 1px solid #4a4e52; border-radius: 4px; padding: 0 8px; }
QPushButton:hover { background: #474b4f; border-color: #6a7075; }
QPushButton:pressed { background: #2d2f31; }
QPushButton[kind="primary"], QPushButton[kind="accent"] {
    background: #3d7fd9; border: 1px solid #5b9cf0; color: #ffffff; font-weight: bold; }
QPushButton[kind="primary"]:hover, QPushButton[kind="accent"]:hover { background: #5b9cf0; }
QPushButton[kind="success"] { background: #2f8f4e; border: 1px solid #43b869; color: #ffffff; font-weight: bold; }
QPushButton[kind="success"]:hover { background: #36a158; }
QPushButton[kind="danger"] { background: #a14646; border: 1px solid #c25a5a; color: #ffffff; }
QPushButton[kind="danger"]:hover { background: #b95555; }
QPushButton[kind="highlight"] { background: #d8942e; border: 1px solid #e8a540; color: #ffffff; font-weight: bold; }
QPushButton[kind="highlight"]:hover { background: #e8a540; }
QPushButton[kind="dry"] { background: #2d2f31; border: 1px solid #3a3d40; color: #7d8289; }
QPushButton[kind="dry"]:hover { background: #343638; }
QPushButton[kind="flat"] { background: #3a3d40; }
QSlider::groove:horizontal { height: 4px; background: #3a3d40; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #5b9cf0; border-radius: 2px; }
QSlider::add-page:horizontal { background: #3a3d40; border-radius: 2px; }
QSlider::handle:horizontal { background: #eceff1; width: 12px; margin: -5px 0; border-radius: 6px; }
QSlider::handle:horizontal:hover { background: #ffffff; }
QListWidget { background: #1d1e20; border: 1px solid #3a3d40; border-radius: 4px; outline: none; }
QListWidget::item { padding: 2px 4px; }
QListWidget::item:hover { background: #2d2f31; }
QListWidget::item:selected { background: #3d7fd9; color: #ffffff; }
QListWidget::indicator, QRadioButton::indicator { width: 11px; height: 11px; border: 1px solid #6a7075;
                                                  border-radius: 2px; background: #1d1e20; }
QRadioButton::indicator { border-radius: 6px; }
QListWidget::indicator:checked, QRadioButton::indicator:checked { background: #5b9cf0; border-color: #5b9cf0; }
QTabWidget::pane { border: none; border-top: 1px solid #343638; }
QTabBar::tab { background: #1b1c1e; color: #9aa0a6; padding: 5px 14px; border: none; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { background: #262729; color: #ffffff; border-bottom: 2px solid #5b9cf0; }
QTabBar::tab:hover { color: #ffffff; }
QScrollBar:vertical { background: #1b1c1e; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #4a4e52; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #1d1e20; color: #e8eaed; border: 1px solid #5b9cf0; padding: 3px; }
"""



# ----------------------------------------------------------------------
# MEL scripts run by the Teeth Ctrl / Extra Sliders buttons (embedded unchanged)
# ----------------------------------------------------------------------
TEETH_CTRL_MEL = r'''global proc teethCtrlAdded()
{

    select -r CC_Base_Teeth ;
    duplicate -n "teeth_bs" -rr;
    parent -w;
    
    select -cl  ;
    select -r teeth_bs.vtx[0:1289] teeth_bs.vtx[2642:3822] teeth_bs.vtx[5063:7516] ;
    cluster -n "upper_teeth_";
    select -cl  ;
    joint -n "upper_teeth";
    parentConstraint "upper_teeth_Handle" "upper_teeth";
    delete "upper_teeth_parentConstraint1";
    //setAttr "upper_teeth.jointOrientY" -90;
    select -cl  ;
    
    select -cl  ;
    select -r teeth_bs.vtx[1290:2641] teeth_bs.vtx[3823:5062] teeth_bs.vtx[7517:10091] ;
    cluster -n "lower_teeth_";
    select -cl  ;
    joint -n "lower_teeth";
    parentConstraint "lower_teeth_Handle" "lower_teeth";
    delete "lower_teeth_parentConstraint1";
    //setAttr "lower_teeth.jointOrientY" -90;
    select -cl  ;
    
    delete "upper_teeth_Handle"  "lower_teeth_Handle" ;
    skinCluster -n "testSkinCluster" -tsb "upper_teeth" "lower_teeth" "teeth_bs";
    
    
    {
        // --- Configuration ---
        string $targetJoint   = "upper_teeth";
        float  $weightVal     = 1.0; 
        string $targetMesh    = "teeth_bs";
    
        string $vtxList[]   = {
            "teeth_bs.vtx[0:1289]", 
            "teeth_bs.vtx[2642:3822]", 
            "teeth_bs.vtx[5063:7516]"
        };
    
        // --- Auto-Find SkinCluster ---
        string $currentSkinCluster = `findRelatedSkinCluster $targetMesh`;
    
        // --- Execution ---
        if ($currentSkinCluster == "") {
            error ("Could not find a valid skinCluster on '" + $targetMesh + "'. Check if the mesh is bound.");
        } else {
            for ($vertexRange in $vtxList) {
                skinPercent -transformValue $targetJoint $weightVal $currentSkinCluster $vertexRange;
            }
            print ("Successfully updated weights for " + $targetMesh + " using " + $currentSkinCluster + ".\n");
        }
    };
    
    
    {
        // --- Configuration ---
        string $targetJoint   = "lower_teeth";
        float  $weightVal     = 1.0; 
        string $targetMesh    = "teeth_bs";
    
        string $vtxList[]   = {
            "teeth_bs.vtx[1290:2641]", 
            "teeth_bs.vtx[3823:5062]", 
            "teeth_bs.vtx[7517:10091]"
        };
    
        // --- Auto-Find SkinCluster ---
        string $currentSkinCluster = `findRelatedSkinCluster $targetMesh`;
    
        // --- Execution ---
        if ($currentSkinCluster == "") {
            error ("Could not find a valid skinCluster on '" + $targetMesh + "'. Check if the mesh is bound.");
        } else {
            for ($vertexRange in $vtxList) {
                skinPercent -transformValue $targetJoint $weightVal $currentSkinCluster $vertexRange;
            }
            print ("Successfully updated weights for " + $targetMesh + " using " + $currentSkinCluster + ".\n");
        }
    };
    
    
    blendShape -e  -t CC_Base_Teeth 2 teeth_bs 1 Morpher_CC_Base_Teeth;
    setAttr "Morpher_CC_Base_Teeth.teeth_bs" 1;
    
    
    select -cl  ;
    circle -c 0 0 0 -nr 0 1 0 -sw 360 -r 5 -d 3 -ut 0 -tol 0.01 -s 8 -ch 1; objectMoveCommand;
    select -r nurbsCircle1.cv[0:3] nurbsCircle1.cv[7] ;
    scale -r -p 0cm 0cm -2.770485cm 1 1 1e-05 ;
    select -cl  ;
    setAttr "nurbsCircleShape1.overrideEnabled" 1;
    setAttr "nurbsCircleShape1.overrideColor" 17;
    rename "nurbsCircle1" "upper_teeth_ctl";
    
    parentConstraint "upper_teeth" "upper_teeth_ctl";
    delete "upper_teeth_ctl_parentConstraint1";
    setAttr "upper_teeth_ctl.rotateY" 0;
    
    select -r upper_teeth_ctl ;
    duplicate -n lower_teeth_ctl ;
    parentConstraint "lower_teeth" "lower_teeth_ctl";
    delete "lower_teeth_ctl_parentConstraint1";
    setAttr "lower_teeth_ctl.rotateY" 0;
    select -cl  ;
    
    
    duplicate upper_teeth_ctl lower_teeth_ctl;
    duplicate upper_teeth_ctl lower_teeth_ctl;
    select -r upper_teeth_ctl1 lower_teeth_ctl1 upper_teeth_ctl2 lower_teeth_ctl2 ;
    pickWalk -d down;
    doDelete;
    rename upper_teeth_ctl1 upper_teeth_ctl_grp;
    rename lower_teeth_ctl1 lower_teeth_ctl_grp;
    rename upper_teeth_ctl2 upper_teeth_jnt_grp;
    rename lower_teeth_ctl2 lower_teeth_jnt_grp;
    
    
    parent upper_teeth_ctl upper_teeth_ctl_grp ;
    parent lower_teeth_ctl lower_teeth_ctl_grp ;
    
    parent upper_teeth upper_teeth_jnt_grp ;
    parent lower_teeth lower_teeth_jnt_grp ;
    
    
    connectAttr -f upper_teeth_ctl.translate upper_teeth.translate;
    connectAttr -f upper_teeth_ctl.rotate upper_teeth.rotate;
    connectAttr -f upper_teeth_ctl.scale upper_teeth.scale;
    
    connectAttr -f lower_teeth_ctl.translate lower_teeth.translate;
    connectAttr -f lower_teeth_ctl.rotate lower_teeth.rotate;
    connectAttr -f lower_teeth_ctl.scale lower_teeth.scale;
    
    parent upper_teeth_ctl_grp CC_Base_UpperJaw ;
    parent lower_teeth_ctl_grp CC_Base_JawRoot ;

}
'''


EXTRA_SLIDERS_MEL = r'''global proc extraSliders()
{

    select -r  FRM_thicknessInward ;
    duplicate -rr;
    move -r -os -wd 0 -6.831893 0 ;
    
    select -r FRM_thicknessInward1.vtx[6:7] ;
    select -tgl FRM_thicknessInward1.vtx[1] ;
    select -tgl FRM_thicknessInward1.vtx[3] ;
    move -r -os -wd 1.133882 0 0 ;
    
    select -r FRM_thicknessInward1|FRM_L_mouth_thicknessInwardU FRM_thicknessInward1|FRM_R_mouth_thicknessInwardU FRM_thicknessInward1|FRM_L_mouth_thicknessInwardD FRM_thicknessInward1|FRM_R_mouth_thicknessInwardD ;
    duplicate -rr;
    move -r 1.043416 0 0 ;
    select -cl  ;
    
    
    rename "FRM_thicknessInward1" "FRM_ExtraShapes";
    
    rename "FRM_ExtraShapes|FRM_L_mouth_thicknessInwardU" "FRM_V_Open";
    rename "FRM_V_Open|CTRL_L_mouth_thicknessInwardU" "CTRL_V_Open";
    
    rename "FRM_ExtraShapes|FRM_R_mouth_thicknessInwardU" "FRM_V_Explosive";
    rename "FRM_V_Explosive|CTRL_R_mouth_thicknessInwardU" "CTRL_V_Explosive";
    
    rename "FRM_ExtraShapes|FRM_L_mouth_thicknessInwardD" "FRM_V_Dental_Lip";
    rename "FRM_V_Dental_Lip|CTRL_L_mouth_thicknessInwardD" "CTRL_V_Dental_Lip";
    
    rename "FRM_ExtraShapes|FRM_R_mouth_thicknessInwardD" "FRM_V_Tight_O";
    rename "FRM_V_Tight_O|CTRL_R_mouth_thicknessInwardD" "CTRL_V_Tight_O";
    
    
    rename "FRM_ExtraShapes|FRM_L_mouth_thicknessInwardU1" "FRM_V_Tight";
    rename "FRM_V_Tight|CTRL_L_mouth_thicknessInwardU" "CTRL_V_Tight";
    
    rename "FRM_ExtraShapes|FRM_R_mouth_thicknessInwardU1" "FRM_V_Wide";
    rename "FRM_V_Wide|CTRL_R_mouth_thicknessInwardU" "CTRL_V_Wide";
    
    rename "FRM_ExtraShapes|FRM_L_mouth_thicknessInwardD1" "FRM_V_Affricate";
    rename "FRM_V_Affricate|CTRL_L_mouth_thicknessInwardD" "CTRL_V_Affricate";
    
    rename "FRM_ExtraShapes|FRM_R_mouth_thicknessInwardD1" "FRM_V_Lip_Open";
    rename "FRM_V_Lip_Open|CTRL_R_mouth_thicknessInwardD" "CTRL_V_Lip_Open";
    
    select -r FRM_ExtraShapes ;
    move -r 1.595882 0 0 ;
    
    
    setAttr "FRM_V_Affricate.rotateZ" 180;
    setAttr "FRM_V_Dental_Lip.rotateZ" 180;
    setAttr "FRM_V_Tight_O.rotateZ" 180;
    setAttr "FRM_V_Lip_Open.rotateZ" 180;
    
    select -r FRM_V_Open.vtx[10:11] ;
    select -tgl FRM_V_Explosive.vtx[10:11] ;
    select -tgl  FRM_V_Tight.vtx[10:11] ;
    select -tgl FRM_V_Wide.vtx[10:11] ;
    move -r 0 -0.739703 0 ;
    select -cl  ;
    select -tgl FRM_V_Dental_Lip.vtx[10:11];
    select -tgl FRM_V_Tight_O.vtx[10:11];
    select -tgl FRM_V_Affricate.vtx[10:11];
    select -tgl FRM_V_Lip_Open.vtx[10:11];
    move -r 0 -0.739703 0 ;
    select -cl  ;
    
    
    transformLimits -ty 0 1 -ety 1 1 CTRL_V_Explosive;
    transformLimits -ty 0 1 -ety 1 1 CTRL_V_Open;
    transformLimits -ty 0 1 -ety 1 1 CTRL_V_Wide;
    transformLimits -ty 0 1 -ety 1 1 CTRL_V_Tight;
    
    transformLimits -ty 0 1 -ety 1 1 CTRL_V_Tight_O;
    transformLimits -ty 0 1 -ety 1 1 CTRL_V_Dental_Lip;
    transformLimits -ty 0 1 -ety 1 1 CTRL_V_Lip_Open;
    transformLimits -ty 0 1 -ety 1 1 CTRL_V_Affricate;
    
    connectAttr -f CTRL_V_Open.translateY Morpher_CC_Base_Body.V_Open;
    connectAttr -f CTRL_V_Explosive.translateY Morpher_CC_Base_Body.V_Explosive;
    connectAttr -f CTRL_V_Dental_Lip.translateY Morpher_CC_Base_Body.V_Dental_Lip;
    connectAttr -f CTRL_V_Tight_O.translateY Morpher_CC_Base_Body.V_Tight_O;
    
    connectAttr -f CTRL_V_Tight.translateY Morpher_CC_Base_Body.V_Tight;
    connectAttr -f CTRL_V_Wide.translateY Morpher_CC_Base_Body.V_Wide;
    connectAttr -f CTRL_V_Affricate.translateY Morpher_CC_Base_Body.V_Affricate;
    connectAttr -f CTRL_V_Lip_Open.translateY Morpher_CC_Base_Body.V_Lip_Open;
    
    select -cl  ;

}
'''



def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None



def _btn(text, kind="default", slot=None, tip=None, height=28):
    b = QtWidgets.QPushButton(text)
    b.setProperty("kind", kind)
    b.setFixedHeight(height)
    b.setCursor(QtCore.Qt.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    if slot:
        b.clicked.connect(guard(slot))
    return b



def _section(title, parent_layout):
    """Plain group (no frame, no title) so sections flow without separators."""
    lay = QtWidgets.QVBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(14)
    parent_layout.addLayout(lay)
    return lay



def _row(*widgets, stretch_first=False):
    h = QtWidgets.QHBoxLayout()
    h.setSpacing(14)
    h.setContentsMargins(0, 0, 0, 0)
    for i, w in enumerate(widgets):
        h.addWidget(w, 1)
    return h



def _label(text, muted=False):
    l = QtWidgets.QLabel(text)
    if muted:
        l.setObjectName("muted")
    return l
