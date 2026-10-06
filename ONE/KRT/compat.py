import maya.OpenMayaUI as omui

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
    IS_PYSIDE6 = True
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance
    IS_PYSIDE6 = False

def get_maya_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QMainWindow) if ptr else None