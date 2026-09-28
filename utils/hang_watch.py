"""Hang watchdog (Stage 58, rewritten v45.2).

v45.2 - WHY THE REWRITE: the first version used faulthandler.dump_traceback_
later(). faulthandler reads other threads' stacks WITHOUT holding the GIL -
it is built for "the process is already dying" moments. Used every 8 s
during a 5-minute Auto Setup FBX import (lots of PyMEL Python running on the
main thread) it read frames while they were changing: the log showed a
garbage frame ('nodetypes.py line 863266405 ... File "kwargs"') right before
Maya crashed. The watchdog itself was the prime crash suspect.

Now it is a plain Python thread using sys._current_frames(), which only runs
while holding the GIL - so it can never read a half-changed frame:
  - a QTimer on the UI thread records "still alive" once a second;
  - the watchdog thread wakes every second; if the UI has been silent for
    more than `threshold` s it logs the UI thread's current Python stack
    (at most once per `threshold` s while the block lasts);
  - if the UI thread is inside C++ and holds the GIL, the watchdog simply
    waits - no stack, but also no risk - and the "responsive again after
    ~Ns" line is still written when the UI comes back.
It also logs any popup/modal dialog that holds all input > POPUP_SECONDS.

Log: <Documents>/maya/KRT/hang_dumps.log
"""
import os
import sys
import threading
import time
import traceback

from ..compat import QtCore, QtWidgets
from .crash_log import _krt_log_dir

POPUP_SECONDS = 10


def _describe(w):
    try:
        geo = w.frameGeometry()
        return "{} title={!r} visible={} geometry=({},{} {}x{})".format(
            type(w).__name__, w.windowTitle(), w.isVisible(),
            geo.x(), geo.y(), geo.width(), geo.height())
    except Exception as e:
        return "{} (describe failed: {})".format(type(w).__name__, e)


class HangWatch(QtCore.QObject):

    def __init__(self, threshold=8, parent=None):
        super(HangWatch, self).__init__(parent)
        self.threshold = threshold
        self.path = os.path.join(_krt_log_dir(), "hang_dumps.log").replace("\\", "/")
        self._lock = threading.Lock()
        self._alive = time.time()          # last UI-thread heartbeat
        self._blocked_logged = 0.0         # when the current block was last logged
        self._in_block = False
        self._stop = threading.Event()
        self._thread = None
        self._main_id = threading.main_thread().ident
        self._grab = None
        self._grab_logged = False
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._heartbeat)

    # ── file ────────────────────────────────────────────────────────────
    def _write(self, text):
        with self._lock:
            try:
                with open(self.path, "a") as f:
                    f.write(text)
            except Exception:
                pass

    # ── UI thread ───────────────────────────────────────────────────────
    def start(self):
        old = getattr(sys, "_krt_hang_watch", None)   # one per Maya session
        if old is not None and old is not self:
            try:
                old.stop()
            except Exception:
                pass
        sys._krt_hang_watch = self
        self._write("\n=== KRT session start {} (threshold {}s, v45.2 GIL-safe watchdog) ===\n".format(
            time.strftime("%Y-%m-%d %H:%M:%S"), self.threshold))
        self._alive = time.time()
        self._timer.start()
        self._thread = threading.Thread(target=self._watch, name="KRT_HangWatch", daemon=True)
        self._thread.start()
        print("[KRT] hang watchdog on - freezes over {}s are logged to {}".format(self.threshold, self.path))
        return True

    def _heartbeat(self):
        now = time.time()
        if self._in_block:
            self._write("--- UI responsive again at {} after ~{:.0f}s blocked ---\n".format(
                time.strftime("%H:%M:%S"), now - self._alive))
            self._in_block = False
        self._alive = now
        self._check_input_grab(now)

    def _check_input_grab(self, now):
        app = QtWidgets.QApplication.instance()
        w = app.activePopupWidget() or app.activeModalWidget()
        if w is None:
            self._grab, self._grab_logged = None, False
            return
        if self._grab is None or self._grab[0] != id(w):
            self._grab, self._grab_logged = (id(w), now), False
            return
        if not self._grab_logged and now - self._grab[1] > POPUP_SECONDS:
            kind = "popup/menu" if app.activePopupWidget() is w else "modal dialog"
            self._write("--- {} {} holding all input for >{}s: {}\n".format(
                time.strftime("%H:%M:%S"), kind, POPUP_SECONDS, _describe(w)))
            self._grab_logged = True

    # ── watchdog thread ─────────────────────────────────────────────────
    def _watch(self):
        while not self._stop.wait(1.0):
            now = time.time()
            silent = now - self._alive
            if silent < self.threshold or now - self._blocked_logged < self.threshold:
                continue
            self._in_block = True
            self._blocked_logged = now
            # Holding the GIL here (we are running Python), so the frames
            # below cannot change while we read them.
            frame = sys._current_frames().get(self._main_id)
            stack = "".join(traceback.format_stack(frame)) if frame else "  <no Python frame>\n"
            self._write("Blocked {:.0f}s at {} - UI thread stack:\n{}".format(
                silent, time.strftime("%H:%M:%S"), stack))

    def stop(self):
        self._timer.stop()
        self._stop.set()
