"""Rig & Model Status tab: every asset of a project with its latest model and latest rig.

Folder layout read (nothing is ever written):
    <project root>/<asset>/model/*.abc|fbx|obj|ma|mb|blend   latest model file
    <project root>/<asset>/rig/*.json|ma|mb                  latest rig file
A rig is RED when the latest model file is newer than the latest rig file (the rig was built on an older
model), GREEN when the rig is at least as new as the model.
"""
import os
import re
import time
from ._shared import *

DEFAULT_STATUS_ROOT = r"P:\rigging_team\Rigging_local_share"
_MODEL_EXT = (".abc", ".fbx", ".obj", ".ma", ".mb", ".blend")
_RIG_EXT = (".json", ".ma", ".mb")
_RED = "#ef9a9a"
_GREEN = "#a5d6a7"
_GREY = "#9e9e9e"


def _latest(folder, exts):
    """-> (path, mtime) of the newest file with one of `exts` in `folder`, or ('', 0)."""
    best, best_t = "", 0.0
    try:
        for n in os.listdir(folder):
            if not n.lower().endswith(exts):
                continue
            p = os.path.join(folder, n)
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
        mdir, rdir = os.path.join(a, "model"), os.path.join(a, "rig")
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
        btn_browse = QtWidgets.QPushButton("...")
        btn_browse.setFixedWidth(34)
        btn_browse.setToolTip("Pick a different project folder")
        bar.addWidget(btn_browse)
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
        btn_browse.clicked.connect(self._status_browse)
        return w

    # ── data ──
    def _status_fill_projects(self):
        self.status_project.blockSignals(True)
        self.status_project.clear()
        root = DEFAULT_STATUS_ROOT
        try:
            for n in sorted(os.listdir(root), key=str.lower):
                p = os.path.join(root, n)
                if not n.startswith(".") and os.path.isdir(p):
                    self.status_project.addItem(n, p)
        except OSError:
            pass
        want = "all_Rigs"
        try:
            rr = (self.get_rig_root() or "").replace("\\", "/").rstrip("/")
            if rr:
                want = os.path.basename(os.path.dirname(rr)) or want
        except Exception:
            pass
        i = self.status_project.findText(want)
        self.status_project.setCurrentIndex(i if i >= 0 else 0)
        self.status_project.blockSignals(False)

    def _status_browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select project folder", DEFAULT_STATUS_ROOT)
        if d:
            d = d.replace("/", os.sep)
            i = self.status_project.findData(d)
            if i < 0:
                self.status_project.addItem(os.path.basename(d) or d, d)
                i = self.status_project.count() - 1
            self.status_project.setCurrentIndex(i)

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
