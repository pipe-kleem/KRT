"""Auto-split from widgets.py."""
from ._shared import *


# ==========================================================================
# PBCameraViewWidget (Playblast tab, request #1): a LIVE embedded Maya
# viewport, adapted from Studio Library's own mutils/gui/modelpanelwidget.py
# (ModelPanelWidget) - see that file for the reference implementation this
# is based on. Embeds a real native Maya modelPanel inside this Qt widget by
# parenting into this widget's own layout via cmds.setParent(...) right
# before creating the modelPanel, then strips it down to a clean 3D view
# (no menu bar/toolbar/HUD) and locks it onto whichever camera the
# Playblast tab's Camera field names.
#
# IMPORTANT / NOT VERIFIABLE IN THIS SANDBOX: embedding a native Maya
# modelPanel into a Qt layout via cmds.setParent + cmds.modelPanel(...) is
# a Maya-UI-bridge operation with no Python-level simulation possible
# outside real Maya + Qt - unlike the rest of KRT's logic, this class's
# core embedding/camera-lock/live-navigation behavior could NOT be
# exercised against stubs and has only been checked for syntax
# (py_compile) and by close reading against Studio Library's own proven
# implementation. Please verify by opening the Playblast tab in real Maya.
# ==========================================================================
class PBCameraViewWidget(QtWidgets.QWidget):
    """Live embedded Maya viewport for the Playblast tab's preview area.
    Navigate with the normal Maya viewport controls (Alt+LMB tumble,
    Alt+MMB pan, Alt+RMB/scroll zoom) once this widget has focus/the mouse
    is over it - Maya's own modelPanel handles that natively, nothing
    special is done here for it. A small 🔒/🔓 lock button sits in the
    top-left corner; when locked, the camera's translate/rotate channels
    are Maya-attribute-locked so tumble/pan/dolly can't move it by
    accident. While unlocked, a QTimer polls the camera's live
    position/rotation and pushes them into the Playblast tab's Position/
    Rotation fields in real time (skipping any field the user is actively
    typing into)."""

    POLL_INTERVAL_MS = 200

    def __init__(self, parent=None, on_transform_changed=None):
        super(PBCameraViewWidget, self).__init__(parent)
        self._camera = None
        self._locked = False
        self._on_transform_changed = on_transform_changed
        self._model_panel = None
        self._last_pushed = None

        uniqueName = "KRT_pbCamView" + str(id(self))
        self._panel_name = uniqueName

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setLayout(outer)

        self._viewport_container = QtWidgets.QWidget(self)
        vlayout = QtWidgets.QVBoxLayout(self._viewport_container)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setObjectName(uniqueName + "Layout")
        self._viewport_container.setLayout(vlayout)
        outer.addWidget(self._viewport_container)

        self._built = False
        try:
            self._build_model_panel(vlayout)
        except Exception as e:
            self._built = False
            fallback = QtWidgets.QLabel(
                "Live camera view unavailable ({}).\n"
                "Generate or set a camera, then re-open this tab.".format(e))
            fallback.setAlignment(QtCore.Qt.AlignCenter)
            fallback.setWordWrap(True)
            fallback.setStyleSheet("color:#888; padding:30px;")
            vlayout.addWidget(fallback)

        # ── Lock toggle button, small, top-left corner of the black
        # screen (per the user's request) ───────────────────────────────
        self.btn_lock = QtWidgets.QPushButton("🔓", self)
        self.btn_lock.setFixedSize(22, 22)
        self.btn_lock.setToolTip("Lock/unlock the camera (prevents accidental tumble/pan/dolly).")
        self.btn_lock.setStyleSheet(
            "QPushButton { background-color: rgba(30,30,30,180); color:white; "
            "border: 1px solid #555; border-radius: 3px; font-size: 11px; } "
            "QPushButton:hover { background-color: rgba(60,60,60,220); }")
        self.btn_lock.clicked.connect(self.toggle_lock)
        self.btn_lock.move(6, 6)
        self.btn_lock.raise_()

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll_camera_transform)
        self._timer.start()

    # -- construction -----------------------------------------------------
    def _build_model_panel(self, vlayout):
        cmds.setParent(vlayout.objectName())
        self._model_panel = cmds.modelPanel(self._panel_name, label="KRT Playblast Camera View")
        self._configure_model_panel()
        self._disable_cached_playback()
        self._built = True

    def _disable_cached_playback(self):
        """A second live viewport (this one) makes Maya's Cached Playback
        system evaluate/cache the scene for one more panel at once, which
        is what was producing the 'Cached Playback: Out of memory... "
        caching has stopped' warnings once this tab's live view opened.
        Cached Playback only speeds up scrubbing/looping in the Time
        Slider - it isn't needed for playblasting or for this tumble/pan
        preview - so it's turned off for the session the moment this
        widget is created, freeing that memory back up rather than
        letting Maya keep fighting for it. Uses Maya's own documented
        toggle (maya.plugin.evaluator.cache_preferences); if that module
        isn't available (older Maya), this is a harmless no-op."""
        try:
            import maya.plugin.evaluator.cache_preferences as cache_preferences
            cache_preferences.CachePreferenceEnabled().set_value(False)
        except Exception:
            try:
                cmds.evaluator(name="cache", enable=False)
            except Exception:
                pass

    def _configure_model_panel(self):
        panel = self._model_panel
        if not panel:
            return
        for flag, value in (
            ("allObjects", False), ("grid", False), ("dynamics", False),
            ("activeOnly", False), ("manipulators", False),
            ("headsUpDisplay", False), ("selectionHiliteDisplay", False),
            ("polymeshes", True), ("nurbsSurfaces", True),
            ("subdivSurfaces", True), ("displayTextures", True),
        ):
            try:
                cmds.modelEditor(panel, edit=True, **{flag: value})
            except Exception:
                pass
        try:
            cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded")
        except Exception:
            pass
        try:
            cmds.modelPanel(panel, edit=True, menuBarVisible=False)
        except Exception:
            pass
        self._hide_bar_layout()

    def _hide_bar_layout(self):
        """Hides the modelPanel's own toolbar (the row of icons above the
        viewport, including the camera-name dropdown) by wrapping its
        native Maya UI control as a Qt WIDGET (not a bare QObject - a
        QObject has no .hide(), so this silently no-op'd before, leaving
        the toolbar visible) and calling .hide() on it - the exact
        technique Studio Library's own ModelPanelWidget.hideBarLayout()
        uses (MQtUtil.findControl + wrapInstance(..., QWidget)). This is
        also the likely fix for the 'updateModelPanelBar ... Syntax
        error' spam some users saw on camera-change/lock - Maya tries to
        refresh that toolbar's camera-name dropdown on those events, and
        with the toolbar actually hidden (this bug fixed) there should be
        nothing left for it to refresh."""
        try:
            import maya.OpenMayaUI as omui
            from .compat import wrapInstance
            bar_name = cmds.modelPanel(self._model_panel, query=True, barLayout=True)
            ptr = omui.MQtUtil.findControl(bar_name)
            if ptr:
                bar_widget = wrapInstance(int(ptr), QtWidgets.QWidget)
                bar_widget.hide()
        except Exception:
            pass

    @staticmethod
    def _quiet_script_editor(fn, *args, **kwargs):
        """Belt-and-suspenders for the 'updateModelPanelBar ... Syntax
        error' spam some Maya installs print on a camera-name refresh for
        this deeply-Qt-nested embedded panel (QStackedWidget/QSplitter/
        tab layers between this modelPanel and KRT's main window, unlike
        Studio Library's own much shallower embedding) - temporarily
        silences the Script Editor's error/warning output only around the
        one call that triggers it, so a harmless internal refresh
        hiccup doesn't spam the user's console. Restores the previous
        suppress state afterward either way, and never swallows a real
        Python exception raised by `fn` itself."""
        prev_err = prev_warn = None
        try:
            prev_err = cmds.scriptEditorInfo(query=True, suppressErrors=True)
            prev_warn = cmds.scriptEditorInfo(query=True, suppressWarnings=True)
            cmds.scriptEditorInfo(suppressErrors=True, suppressWarnings=True)
        except Exception:
            prev_err = prev_warn = None
        try:
            return fn(*args, **kwargs)
        finally:
            if prev_err is not None or prev_warn is not None:
                try:
                    cmds.scriptEditorInfo(
                        suppressErrors=bool(prev_err), suppressWarnings=bool(prev_warn))
                except Exception:
                    pass

    # -- camera control -----------------------------------------------------
    def set_camera(self, camera_name):
        """Points this embedded viewport at `camera_name` (a transform or
        shape). Safe to call repeatedly (e.g. right after Generate
        Camera, or whenever the Camera field changes)."""
        self._camera = camera_name or None
        if not self._built or not self._camera:
            return
        if not cmds.objExists(self._camera):
            return
        try:
            self._quiet_script_editor(
                cmds.modelPanel, self._model_panel, edit=True, camera=self._camera)
        except Exception:
            pass
        self._apply_lock_state()

    def current_camera(self):
        return self._camera

    def _camera_transform(self):
        if not self._camera or not cmds.objExists(self._camera):
            return None
        if cmds.objectType(self._camera) == "camera":
            parents = cmds.listRelatives(self._camera, parent=True, fullPath=True) or []
            return parents[0] if parents else None
        return self._camera

    def _camera_shape(self):
        tfm = self._camera_transform()
        if not tfm:
            return None
        if cmds.objectType(tfm) == "camera":
            return tfm
        shapes = cmds.listRelatives(tfm, shapes=True, type="camera", fullPath=True) or []
        return shapes[0] if shapes else None

    # -- lock ---------------------------------------------------------------
    def is_locked(self):
        return self._locked

    def toggle_lock(self):
        self.set_locked(not self._locked)

    def set_locked(self, locked):
        self._locked = bool(locked)
        self.btn_lock.setText("🔒" if self._locked else "🔓")
        self.btn_lock.setToolTip(
            "Camera is LOCKED - click to unlock." if self._locked
            else "Camera is unlocked - click to lock (prevents accidental tumble/pan/dolly).")
        self._apply_lock_state()

    def _apply_lock_state(self):
        """Locking just the camera transform's translate/rotate ATTRIBUTES
        (what this used to do) does NOT stop Maya's own tumble/track/dolly
        tools - the viewport navigation manipulator writes the camera's
        transformation matrix as a whole, which isn't blocked by locking
        individual channels the same way a Channel Box edit would be. The
        actual fix is Maya's own per-camera 'lockTransform' flag on the
        camera SHAPE (cmds.camera(..., lockTransform=True)) - that's the
        real 'stop the viewport from moving this camera at all' switch
        or-drag Maya itself uses. Both are applied here: lockTransform
        does the real work, and the plain attribute lock is kept as a
        secondary guard against an accidental Channel Box/Attribute
        Editor edit while lockTransform isn't available (older Maya)."""
        tfm = self._camera_transform()
        shape = self._camera_shape()
        if shape:
            try:
                self._quiet_script_editor(
                    cmds.camera, shape, edit=True, lockTransform=self._locked)
            except Exception:
                pass
        if not tfm:
            return
        for attr in ("translateX", "translateY", "translateZ",
                     "rotateX", "rotateY", "rotateZ"):
            plug = "{}.{}".format(tfm, attr)
            if cmds.objExists(plug):
                try:
                    cmds.setAttr(plug, lock=self._locked)
                except Exception:
                    pass

    # -- real-time position/rotation sync -----------------------------------
    def _poll_camera_transform(self):
        if self._locked:
            return
        tfm = self._camera_transform()
        if not tfm or not cmds.objExists(tfm):
            return
        try:
            pos = cmds.xform(tfm, query=True, translation=True, worldSpace=True)
            rot = cmds.xform(tfm, query=True, rotation=True, worldSpace=True)
        except Exception:
            return
        values = tuple(round(v, 4) for v in (pos + rot))
        if values == self._last_pushed:
            return
        self._last_pushed = values
        if self._on_transform_changed:
            try:
                self._on_transform_changed(pos, rot)
            except Exception:
                pass

    # -- cleanup --------------------------------------------------------------
    def stop(self):
        if self._timer.isActive():
            self._timer.stop()

    def closeEvent(self, event):
        self.stop()
        super(PBCameraViewWidget, self).closeEvent(event)

    def resizeEvent(self, event):
        super(PBCameraViewWidget, self).resizeEvent(event)
        # Keep the lock button pinned to the top-left corner as the widget
        # resizes (it's a child of self, not of the layout, so it doesn't
        # reflow automatically).
        self.btn_lock.move(6, 6)


# ==========================================================================
# PBWipeCompareWidget (Playblast tab, request #6): two playblasts played
# back-to-back with a draggable vertical divider - everything left of the
# line shows clip A, everything right shows clip B, so scrubbing/dragging
# the line back and forth over the same moment shows exactly what changed
# between two versions of the same shot.
#
# PySide6/Qt6-only: this needs raw decoded video FRAMES (QVideoSink's
# videoFrameChanged) to paint two clips clipped against each other in one
# widget - a plain QVideoWidget is a native window that always draws on
# top of everything else regardless of Qt stacking order, so it can't be
# masked/overlaid this way. Qt5/PySide2 has no public equivalent of
# QVideoSink, so this widget shows a plain explanation message there
# instead of a video (see is_available()) - pb_toggle_compare_mode() in
# workspace.py falls back to the existing side-by-side compare page in
# that case.
# ==========================================================================
class PBWipeCompareWidget(QtWidgets.QWidget):
    HANDLE_GRAB_PX = 18

    def __init__(self, parent=None):
        super(PBWipeCompareWidget, self).__init__(parent)
        self.setMinimumHeight(300)
        self.setMouseTracking(True)
        self.setStyleSheet("background:#000;")
        self._slider_frac = 0.5
        self._pix_a = None
        self._pix_b = None
        self._dragging = False
        self._player_a = None
        self._player_b = None
        self._sink_a = None
        self._sink_b = None
        self._built = False
        self._label_a = "A"
        self._label_b = "B"
        try:
            self._build_players()
            self._built = True
        except Exception:
            self._built = False

    def is_available(self):
        return self._built

    def _build_players(self):
        from .compat import QMediaPlayer, QVideoSink, HAS_VIDEO_SINK
        if not HAS_VIDEO_SINK or QMediaPlayer is None:
            raise RuntimeError("QVideoSink not available (needs PySide6/Qt6 multimedia)")

        self._player_a = QMediaPlayer(self)
        self._sink_a = QVideoSink(self)
        self._player_a.setVideoSink(self._sink_a)
        self._sink_a.videoFrameChanged.connect(self._on_frame_a)

        self._player_b = QMediaPlayer(self)
        self._sink_b = QVideoSink(self)
        self._player_b.setVideoSink(self._sink_b)
        self._sink_b.videoFrameChanged.connect(self._on_frame_b)

    def _on_frame_a(self, frame):
        try:
            img = frame.toImage()
        except Exception:
            return
        if img is not None and not img.isNull():
            self._pix_a = QtGui.QPixmap.fromImage(img)
            self.update()

    def _on_frame_b(self, frame):
        try:
            img = frame.toImage()
        except Exception:
            return
        if img is not None and not img.isNull():
            self._pix_b = QtGui.QPixmap.fromImage(img)
            self.update()

    def load(self, path_a, path_b, label_a="A", label_b="B"):
        self._label_a = label_a or "A"
        self._label_b = label_b or "B"
        self._pix_a = None
        self._pix_b = None
        if not self._built:
            self.update()
            return
        self._player_a.setSource(QtCore.QUrl.fromLocalFile(path_a))
        self._player_b.setSource(QtCore.QUrl.fromLocalFile(path_b))
        self.update()

    def play(self):
        if self._built:
            self._player_a.play()
            self._player_b.play()

    def pause(self):
        if self._built:
            self._player_a.pause()
            self._player_b.pause()

    def stop(self):
        if self._built:
            self._player_a.stop()
            self._player_b.stop()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#000"))

        if not self._built:
            painter.setPen(QtGui.QColor("#ffcc66"))
            painter.drawText(
                self.rect(), QtCore.Qt.AlignCenter,
                "Wipe compare needs PySide6/Qt6 multimedia (QVideoSink),\n"
                "which isn't available in this Maya's Qt install.\n"
                "Use Side-by-Side compare mode instead.")
            painter.end()
            return

        w, h = self.width(), self.height()
        divider_x = int(w * self._slider_frac)

        if self._pix_a is not None:
            scaled_a = self._pix_a.scaled(
                w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            ax = (w - scaled_a.width()) // 2
            ay = (h - scaled_a.height()) // 2
            painter.setClipRect(0, 0, max(0, divider_x), h)
            painter.drawPixmap(ax, ay, scaled_a)
            painter.setClipping(False)

        if self._pix_b is not None:
            scaled_b = self._pix_b.scaled(
                w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            bx = (w - scaled_b.width()) // 2
            by = (h - scaled_b.height()) // 2
            painter.setClipRect(divider_x, 0, max(0, w - divider_x), h)
            painter.drawPixmap(bx, by, scaled_b)
            painter.setClipping(False)

        # Divider line + drag handle
        painter.setPen(QtGui.QPen(QtGui.QColor("#2bb5a8"), 2))
        painter.drawLine(divider_x, 0, divider_x, h)
        painter.setBrush(QtGui.QColor("#2bb5a8"))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(QtCore.QPoint(divider_x, h // 2), 8, 8)

        # A/B labels, top-left / top-right of each side
        painter.setPen(QtGui.QColor("#ffffff"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QtCore.QRect(6, 4, 200, 20), QtCore.Qt.AlignLeft, self._label_a)
        painter.drawText(QtCore.QRect(w - 206, 4, 200, 20), QtCore.Qt.AlignRight, self._label_b)
        painter.end()

    def _divider_px(self):
        return int(self.width() * self._slider_frac)

    def mousePressEvent(self, event):
        if abs(event.pos().x() - self._divider_px()) <= self.HANDLE_GRAB_PX:
            self._dragging = True
        else:
            # Click-anywhere-to-move, same convenience as most wipe-compare
            # UIs (Delta/Before-After sliders) - not just drag-from-the-line.
            self._set_slider_from_x(event.pos().x())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._set_slider_from_x(event.pos().x())

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def _set_slider_from_x(self, x):
        self._slider_frac = min(1.0, max(0.0, x / float(max(1, self.width()))))
        self.update()
