# -*- coding: utf-8 -*-
"""
maya_playblast_viewer.py
Temporary window that plays the wrinkle check ONCE, with SMOOTH fades:
for every wrinkle channel the wrinkle eases in (0 -> 100 %), holds, and eases back out.
Between the rendered strengths the images are cross-blended, so it is a smooth
animation and not just an on/off flip.  Sliders let you scrub channel and strength.

Nothing is added to the Maya scene. Closing the window deletes the temporary frames,
so the playblast can only be viewed this one time.
"""
import os
import json
import shutil
from collections import OrderedDict

try:                                    # Maya 2025+
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:                     # Maya 2017-2024
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

_WINDOW = None   # keep a reference so the window is not garbage collected


def _maya_main_window():
    try:
        from maya import OpenMayaUI as omui
        ptr = omui.MQtUtil.mainWindow()
        return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None
    except Exception:
        return None


def _smoothstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def strength_at(u, fade, hold):
    """Wrinkle strength (0..1) at local time u of one channel: fade in, hold, fade out."""
    if u < fade:
        return _smoothstep(u / fade)
    if u < fade + hold:
        return 1.0
    return _smoothstep(1.0 - (u - fade - hold) / fade)


class WrinklePlayblastWindow(QtWidgets.QDialog):
    CACHE_SIZE = 48
    TICK_MS = 30

    def __init__(self, folder, data, fade=0.6, hold=0.25, parent=None, on_import=None, on_reject=None):
        super(WrinklePlayblastWindow, self).__init__(parent)
        self._folder = folder
        self._on_import = on_import
        self._on_reject = on_reject
        self._channels = data["channels"]
        self._steps = int(data["steps"])
        self._neutral = data["neutral"]
        self._fade, self._hold = float(fade), float(hold)
        self._period = 2.0 * self._fade + self._hold
        self._total = self._period * len(self._channels)
        self._cache = OrderedDict()
        self._media = 0.0           # seconds into the whole timeline
        self._speed = 1.0
        self._c, self._s = 0, 0.0

        self.setWindowTitle("Wrinkle Playblast (temporary - closes for good)")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        self.image = QtWidgets.QLabel()
        self.image.setAlignment(QtCore.Qt.AlignCenter)
        self.image.setMinimumSize(480, 480)
        self.image.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)

        self.caption = QtWidgets.QLabel()
        self.caption.setAlignment(QtCore.Qt.AlignCenter)
        self.caption.setStyleSheet("font-weight: bold; font-size: 13px;")

        self.button = QtWidgets.QPushButton("Pause")
        self.button.clicked.connect(self._toggle)
        self.speed = QtWidgets.QComboBox()
        for label, v in (("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("4x", 4.0)):
            self.speed.addItem(label, v)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(
            lambda _i: setattr(self, "_speed", float(self.speed.currentData())))

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.button)
        top.addWidget(QtWidgets.QLabel("Speed"))
        top.addWidget(self.speed)
        top.addStretch(1)

        self.ch_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.ch_slider.setRange(0, len(self._channels) - 1)
        self.ch_slider.valueChanged.connect(self._user_channel)
        self.st_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.st_slider.setRange(0, 100)
        self.st_slider.valueChanged.connect(self._user_strength)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("Wrinkle"), 0, 0)
        grid.addWidget(self.ch_slider, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Strength"), 1, 0)
        grid.addWidget(self.st_slider, 1, 1)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.image, 1)
        lay.addWidget(self.caption)
        lay.addLayout(grid)
        lay.addLayout(top)
        if on_import is not None:        # artist judges the wrinkles FIRST, then decides
            row = QtWidgets.QHBoxLayout()
            ok = QtWidgets.QPushButton("Wrinkles OK  -  Import ABC into Maya")
            ok.setStyleSheet("font-weight: bold; padding: 8px;")
            ok.clicked.connect(self._do_import)
            no = QtWidgets.QPushButton("Wrinkles NOT OK  -  Don't import")
            no.setStyleSheet("padding: 8px;")
            no.clicked.connect(self.close)
            row.addWidget(ok)
            row.addWidget(no)
            lay.addLayout(row)
        self.resize(700, 860)

        self._clock = QtCore.QElapsedTimer()
        self._last = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._set_state(0, 0.0)
        self._play()

    # -- images ------------------------------------------------------------
    def _load(self, name):
        img = self._cache.get(name)
        if img is None:
            img = QtGui.QImage(os.path.join(self._folder, name)).convertToFormat(QtGui.QImage.Format_RGB32)
            self._cache[name] = img
            while len(self._cache) > self.CACHE_SIZE:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(name)
        return img

    def _step_image(self, c, k):
        """k = 0 -> neutral, k = 1..steps -> rendered strength k/steps of channel c."""
        if k <= 0:
            return self._load(self._neutral)
        return self._load(self._channels[c]["frames"][k - 1])

    def _blended(self, c, s):
        x = max(0.0, min(1.0, s)) * self._steps
        k0 = min(int(x), self._steps)
        k1 = min(k0 + 1, self._steps)
        t = x - k0
        a = self._step_image(c, k0)
        if t < 0.01 or k1 == k0:
            return a
        b = self._step_image(c, k1)
        out = QtGui.QImage(a.size(), QtGui.QImage.Format_RGB32)
        p = QtGui.QPainter(out)
        p.drawImage(0, 0, a)
        p.setOpacity(t)
        p.drawImage(0, 0, b)
        p.end()
        return out

    # -- state -------------------------------------------------------------
    def _set_state(self, c, s):
        self._c, self._s = c, s
        for w, v in ((self.ch_slider, c), (self.st_slider, int(round(s * 100)))):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self._show()

    def _show(self):
        ch = self._channels[self._c]
        self._pixmap = QtGui.QPixmap.fromImage(self._blended(self._c, self._s))
        self._fit()
        self.caption.setText("%s     strength %3d %%     (%d / %d)" % (
            ch["label"], int(round(self._s * 100)), self._c + 1, len(self._channels)))

    def _fit(self):
        pm = getattr(self, "_pixmap", None)
        if pm is not None and not pm.isNull():
            self.image.setPixmap(pm.scaled(self.image.size(), QtCore.Qt.KeepAspectRatio,
                                           QtCore.Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super(WrinklePlayblastWindow, self).resizeEvent(event)
        self._fit()

    # -- playback (plays ONCE through all channels, then holds) ---------------
    def _now(self):
        return self._clock.elapsed() / 1000.0

    def _play(self):
        if self._media >= self._total:
            self._media = 0.0
        self._clock.start()
        self._last = 0.0
        self._timer.start()
        self.button.setText("Pause")

    def _pause(self, text="Play"):
        self._timer.stop()
        self.button.setText(text)

    def _toggle(self):
        if self._timer.isActive():
            self._pause()
        else:
            self._play()

    def _tick(self):
        now = self._now()
        self._media += (now - self._last) * self._speed
        self._last = now
        if self._media >= self._total:                # finished: hold on the last channel
            self._set_state(len(self._channels) - 1, 0.0)
            self._pause("Replay")
            return
        c = int(self._media // self._period)
        u = self._media - c * self._period
        self._set_state(c, strength_at(u, self._fade, self._hold))

    def _user_channel(self, v):
        self._pause()
        self._media = v * self._period
        self._set_state(v, self._s)

    def _user_strength(self, v):
        self._pause()
        self._set_state(self._c, v / 100.0)

    def _do_import(self):
        cb, self._on_import = self._on_import, None
        self.close()                       # frames are temporary, deleted on close
        if cb:
            cb()

    def closeEvent(self, event):
        self._timer.stop()
        shutil.rmtree(self._folder, ignore_errors=True)   # temporary: gone after closing
        global _WINDOW
        _WINDOW = None
        # Closed WITHOUT pressing 'Wrinkles OK' (NOT OK button or the X): tell the caller.
        rej, self._on_reject = self._on_reject, None
        if self._on_import is not None and rej:
            self._on_import = None
            try:
                rej()
            except Exception:
                import traceback; traceback.print_exc()
        super(WrinklePlayblastWindow, self).closeEvent(event)


def show(folder, fade=0.6, hold=0.25, fps=None, on_import=None, on_reject=None, **_ignored):
    """Open the temporary player for a folder written by blender_playblast.py.
    fade = seconds to fade a wrinkle in (and the same to fade out), hold = seconds at full.
    (fps and any other old arguments are accepted and ignored, so an older pasted copy of
    run_in_maya.py still works.)"""
    global _WINDOW
    manifest = os.path.join(folder, "manifest.json")
    if not os.path.isfile(manifest):
        raise IOError("No playblast found in " + folder)
    with open(manifest) as f:
        data = json.load(f)
    if not data.get("channels"):
        raise RuntimeError("Playblast has no wrinkle channels with a visible change.")

    if data.get("missing_textures"):
        print("[wrinkle playblast] WARNING missing textures: %s" % ", ".join(data["missing_textures"]))
    if data.get("skipped"):
        print("[wrinkle playblast] channels with NO visible change (check mask/texture): %s"
              % ", ".join(data["skipped"]))

    if _WINDOW is not None:
        _WINDOW.close()
    _WINDOW = WrinklePlayblastWindow(folder, data, fade, hold, _maya_main_window(), on_import, on_reject)
    _WINDOW.show()
    _WINDOW.raise_()
    return _WINDOW
