"""Rig & Model Status tab: every asset of a project with its latest model and latest rig.

Folder layout read (nothing is ever written):
    <project root>/<root>/<asset>/publish/workfile/workfileMaster_model/vNN/*.blend   latest model
    <root>/<asset>/publish/rig/rigMain/vNN/*.ma                        latest rig
A rig is RED when the latest model file is newer than the latest rig file (the rig was built on an older
model), GREEN when the rig is at least as new as the model.
"""
import os
import re
import time
from ._shared import *

DEFAULT_STATUS_ROOT = r"P:\kl_assets\KL_ASSETS\assets"      # READ ONLY: server folder, only listed / dated, never written
_MODEL_SUB = ("publish", "workfile", "workfileMaster_model")
_RIG_SUB = ("publish", "rig", "rigMain")
_MODEL_EXT = (".blend",)
_RIG_EXT = (".ma", ".mb")
_RED = "#ef9a9a"
_GREEN = "#a5d6a7"
_GREY = "#9e9e9e"


def _latest(base, exts):
    """-> (path, mtime) of the file with one of `exts` inside the highest vNN folder of `base`
    (<base>/vNN/<file>). Only lists folders and reads dates - nothing is written."""
    best_n, best_dir = -1, ""
    try:
        for n in os.listdir(base):
            m = re.match(r"^v(\d+)$", n, re.I)
            if m and int(m.group(1)) > best_n and os.path.isdir(os.path.join(base, n)):
                best_n, best_dir = int(m.group(1)), os.path.join(base, n)
    except OSError:
        return "", 0.0
    if not best_dir:
        return "", 0.0
    best, best_t = "", 0.0
    try:
        for n in os.listdir(best_dir):
            if n.lower().endswith(exts):
                p = os.path.join(best_dir, n)
                try:
                    t = os.path.getmtime(p)
                except OSError:
                    continue
                if t > best_t:
                    best, best_t = p, t
    except OSError:
        pass
    return best, best_t


def _ver(path):
    """'v04' from a file name (first _vNN / vNN token), '' if none."""
    m = re.search(r"(?:^|[_\-.])v(\d+)", os.path.basename(path), re.I)
    return "v" + m.group(1) if m else ""


def _fmt(t):
    return time.strftime("%d-%m-%Y %H:%M", time.localtime(t)) if t else "-"


def scan_project(root):
    """-> list of dicts, one per asset folder under `root`, sorted by name."""
    rows = []
    try:
        names = sorted(os.listdir(root), key=str.lower)
    except OSError:
        return rows
    for n in names:
        a = os.path.join(root, n)
        if n.startswith(".") or not os.path.isdir(a):
            continue
        mdir, rdir = os.path.join(a, *_MODEL_SUB), os.path.join(a, *_RIG_SUB)
        if not (os.path.isdir(mdir) or os.path.isdir(rdir)):
            continue
        mp, mt = _latest(mdir, _MODEL_EXT)
        rp, rt = _latest(rdir, _RIG_EXT)
        if not mp:
            state = "nomodel"
        elif not rp:
            state = "norig"
        elif rt < mt:
            state = "old"
        else:
            state = "ok"
        rows.append({"asset": n, "model": mp, "model_t": mt, "rig": rp, "rig_t": rt, "state": state})
    return rows


class WorkspaceStatusMixin(object):

    def page_status(self):
        QT = QtCore.Qt
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        title = QtWidgets.QLabel("RIG & MODEL STATUS")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: white; letter-spacing: 1px;")
        lay.addWidget(title)

        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("Project:"))
        self.status_project = QtWidgets.QComboBox()
        self.status_project.setMinimumWidth(240)
        bar.addWidget(self.status_project)
        self.status_search = QtWidgets.QLineEdit()
        self.status_search.setPlaceholderText("Filter assets...")
        self.status_search.setMinimumWidth(200)
        bar.addWidget(self.status_search)
        bar.addStretch()
        self.status_only_old = QtWidgets.QCheckBox("Only outdated")
        bar.addWidget(self.status_only_old)
        btn_refresh = QtWidgets.QPushButton("Refresh")
        btn_refresh.setToolTip("Re-scan the project folders now")
        btn_refresh.setFixedHeight(28)
        bar.addWidget(btn_refresh)
        lay.addLayout(bar)

        self.status_counts = QtWidgets.QLabel("")
        self.status_counts.setStyleSheet("color: #cccccc; font-size: 12px;")
        lay.addWidget(self.status_counts)

        cols = ["Asset", "Model version", "Model saved", "Rig version", "Rig saved", "Status"]
        self.status_table = QtWidgets.QTableWidget(0, len(cols))
        self.status_table.setHorizontalHeaderLabels(cols)
        self.status_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.status_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setAlternatingRowColors(False)
        self.status_table.setSortingEnabled(True)
        hh = self.status_table.horizontalHeader()
        hh.setStretchLastSection(True)
        self.status_table.setStyleSheet(
            "QTableWidget { background: #1e1e1e; color: #dddddd; gridline-color: #2d2d2d; border: 1px solid #333; }"
            "QHeaderView::section { background: #2a2a2a; color: #bbbbbb; padding: 6px; border: none;"
            " border-bottom: 1px solid #3a3a3a; }")
        lay.addWidget(self.status_table, 1)

        self._status_rows = []
        self._status_fill_projects()
        self.status_project.currentIndexChanged.connect(lambda *_: self.status_refresh())
        self.status_search.textChanged.connect(lambda *_: self._status_render())
        self.status_only_old.toggled.connect(lambda *_: self._status_render())
        btn_refresh.clicked.connect(lambda *_: self.status_refresh())
        return w

    # ── data ──
    def _status_fill_projects(self):
        """Project = kl_assets; the dropdown lists its asset categories (characters, ...)."""
        self.status_project.blockSignals(True)
        self.status_project.clear()
        try:
            for n in sorted(os.listdir(DEFAULT_STATUS_ROOT), key=str.lower):
                p = os.path.join(DEFAULT_STATUS_ROOT, n)
                if not n.startswith(".") and os.path.isdir(p):
                    self.status_project.addItem("kl_assets / " + n, p)
        except OSError:
            pass
        i = self.status_project.findText("kl_assets / characters")
        self.status_project.setCurrentIndex(i if i >= 0 else 0)
        self.status_project.blockSignals(False)

    def status_refresh(self):
        root = self.status_project.currentData()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self._status_rows = scan_project(root) if root else []
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._status_render()

    def _status_render(self):
        QT = QtCore.Qt
        rows = self._status_rows
        total = len(rows)
        n_model = sum(1 for r in rows if r["model"])
        n_rig = sum(1 for r in rows if r["rig"])
        n_ok = sum(1 for r in rows if r["state"] == "ok")
        n_old = sum(1 for r in rows if r["state"] == "old")
        n_missing = sum(1 for r in rows if r["state"] in ("norig", "nomodel"))
        self.status_counts.setText(
            "Assets: %d    Models: %d    Rigs: %d    "
            "<span style='color:%s'>Up to date: %d</span>    "
            "<span style='color:%s'>Rig older than model: %d</span>    "
            "<span style='color:%s'>Missing model / rig: %d</span>"
            % (total, n_model, n_rig, _GREEN, n_ok, _RED, n_old, _GREY, n_missing))
        self.status_counts.setTextFormat(QT.RichText)

        flt = self.status_search.text().strip().lower()
        only_old = self.status_only_old.isChecked()
        shown = [r for r in rows if (not flt or flt in r["asset"].lower())
                 and (not only_old or r["state"] in ("old", "norig"))]
        t = self.status_table
        t.setSortingEnabled(False)
        t.setRowCount(len(shown))
        label = {"ok": "Up to date", "old": "Rig older than model", "norig": "No rig", "nomodel": "No model"}
        for i, r in enumerate(shown):
            col = {"ok": _GREEN, "old": _RED, "norig": _RED}.get(r["state"], _GREY)
            tint = QtGui.QColor(col)
            tint.setAlpha(34)
            vals = [r["asset"], _ver(r["model"]) or ("-" if not r["model"] else "?"), _fmt(r["model_t"]),
                    _ver(r["rig"]) or ("-" if not r["rig"] else "?"), _fmt(r["rig_t"]), label[r["state"]]]
            tips = ["", r["model"], r["model"], r["rig"], r["rig"], ""]
            for c, v in enumerate(vals):
                it = QtWidgets.QTableWidgetItem(v)
                it.setToolTip(tips[c])
                it.setBackground(tint)
                if c in (0, 5) or c >= 3:
                    it.setForeground(QtGui.QColor(col))
                t.setItem(i, c, it)
        t.setSortingEnabled(True)
        t.resizeColumnsToContents()
