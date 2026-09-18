import maya.OpenMayaUI as omui

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
    IS_PYSIDE6 = True
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance
    IS_PYSIDE6 = False

# Stage 17: the Playblast panel's embedded video player needs QtMultimedia/
# QtMultimediaWidgets (QMediaPlayer + QVideoWidget). Some Maya installs'
# bundled Qt doesn't ship these (missing plugin/codec backend is a known,
# fairly common gap) - HAS_MULTIMEDIA lets the Playblast page degrade
# gracefully (open in the OS's own player instead of embedding) rather than
# failing to open KRT at all.
try:
    if IS_PYSIDE6:
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtMultimediaWidgets import QVideoWidget
        QMediaContent = None
    else:
        from PySide2.QtMultimedia import QMediaPlayer, QMediaContent
        from PySide2.QtMultimediaWidgets import QVideoWidget
        QAudioOutput = None
    HAS_MULTIMEDIA = True
except ImportError:
    QMediaPlayer = None
    QVideoWidget = None
    QAudioOutput = None
    QMediaContent = None
    HAS_MULTIMEDIA = False

# Stage 40: the Playblast tab's wipe/slider compare mode needs raw decoded
# video FRAMES (to paint two clips overlaid with a draggable divider) rather
# than just an on-screen QVideoWidget - PySide6/Qt6's QVideoSink is what
# hands those frames back via videoFrameChanged. Qt5/PySide2 has no public
# equivalent (would need a custom QAbstractVideoSurface, a much bigger
# lift), so wipe mode is PySide6-only - HAS_VIDEO_SINK lets it degrade to
# the existing side-by-side compare instead of failing to open KRT.
try:
    if IS_PYSIDE6:
        from PySide6.QtMultimedia import QVideoSink
        HAS_VIDEO_SINK = True
    else:
        QVideoSink = None
        HAS_VIDEO_SINK = False
except ImportError:
    QVideoSink = None
    HAS_VIDEO_SINK = False

def get_maya_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QMainWindow) if ptr else None