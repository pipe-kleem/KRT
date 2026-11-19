"""Rig & Model Status tab: every asset of a project with its latest model and latest rig.

Folder layout read (nothing is ever written):
    <project root>/<root>/<asset>/publish/workfile/workfileMaster_model/vNN/*.blend   latest model
    <root>/<asset>/publish/rig/rigMain/vNN/*.ma                        latest rig
A rig is RED when the latest model file is newer than the latest rig file (the rig was built on an older
model), GREEN when the rig is at least as new as the model.
"""
import os
import re
import subprocess
import time
from ._shared import *

DEFAULT_STATUS_ROOT = r"P:\kl_assets\KL_ASSETS\assets"      # READ ONLY: server folder, only listed / dated, never written
_MODEL_SUB = ("publish", "workfile", "workfileMaster_model")
# Props / locations / many characters keep their model in workfileModel_lod instead; the newest file of either counts.
_MODEL_SUBS = (_MODEL_SUB,)      # only workfileMaster_model counts as the model (workfileModel_lod is ignored)
_RIG_SUB = ("publish", "rig", "rigMain")
_CC_SUB = ("publish", "workfile", "workfileCc_model")
_CC_EXT = (".ccproject",)
_MODEL_EXT = (".blend",)
_RIG_EXT = (".ma", ".mb")
_RED = "#ef9a9a"
_GREEN = "#a5d6a7"
_GREY = "#9e9e9e"
# Type tag colours (the Type column is highlighted like a tag): characters / props / locations / anything else
_TYPE_COLORS = {"characters": "#4dd0e1", "props": "#ffb74d", "locations": "#ba68c8"}
_TYPE_OTHER = "#90a4ae"


def _latest(base, exts, cutoff=None):
    """-> (path, mtime) of the file with one of `exts` inside the highest vNN folder of `base`
    (<base>/vNN/<file>). Only lists folders and reads dates - nothing is written."""
    vers = []
    try:
        for n in os.listdir(base):
            m = re.match(r"^v(\d+)$", n, re.I)
            if m and os.path.isdir(os.path.join(base, n)):
                vers.append((int(m.group(1)), os.path.join(base, n)))
    except OSError:
        return "", 0.0
    vers.sort(reverse=True)
    for _n, d in vers:                      # highest version first; with a cutoff, the newest one that existed by then
        best, best_t = "", 0.0
        try:
            for n in os.listdir(d):
                if n.lower().endswith(exts):
                    p = os.path.join(d, n)
                    try:
                        t = os.path.getctime(p)
                    except OSError:
                        continue
                    if cutoff is not None and t >= cutoff:
                        continue
                    if t > best_t:
                        best, best_t = p, t
        except OSError:
            pass
        if best:
            return best, best_t
    return "", 0.0


def _ver(path):
    """'v04' from the file name (first _vNN / vNN token); if the name has none, from the vNN folder it sits in."""
    if not path:
        return ""
    m = re.search(r"(?:^|[_\-.])v(\d+)", os.path.basename(path), re.I)
    if m:
        return "v" + m.group(1)
    m = re.match(r"^v(\d+)$", os.path.basename(os.path.dirname(path)), re.I)
    return "v" + m.group(1) if m else ""


def _fmt(t):
    return time.strftime("%d-%m-%Y %H:%M", time.localtime(t)) if t else "-"


def _find_assets(root, rel="", depth=0):
    """Asset folders = folders that contain 'publish'. A folder without it (e.g. parshuramsubassets) is a group:
    look one or two levels deeper. Only lists folders."""
    out = []
    try:
        names = sorted(os.listdir(root), key=str.lower)
    except OSError:
        return out
    for n in names:
        p = os.path.join(root, n)
        if n.startswith(".") or not os.path.isdir(p):
            continue
        r = (rel + "/" + n) if rel else n
        if os.path.isdir(os.path.join(p, "publish")):
            out.append((r, p))
        elif depth < 3:
            out.extend(_find_assets(p, r, depth + 1))
    return out


def scan_project(root, cutoff=None):
    """-> list of dicts, one per asset (also assets inside group folders), sorted by name. Read only."""
    rows = []
    for rel, a in _find_assets(root):
        atype, _, rel = rel.partition("/")        # first folder under assets = type (characters / props / locations ...)
        if not rel:
            continue
        mp, mt = "", 0.0
        for sub in _MODEL_SUBS:
            p2, t2 = _latest(os.path.join(a, *sub), _MODEL_EXT, cutoff)
            if p2 and t2 >= mt:
                mp, mt = p2, t2
        cp, ct = _latest(os.path.join(a, *_CC_SUB), _CC_EXT, cutoff)
        # Rig = newest .ma/.mb in rigMain/vNN/ OR in a sub-folder of rigMain (e.g. rigMain/rigging/vNNN/*_Rig_built.ma, hero/)
        rp, rt = "", 0.0
        rbase = os.path.join(a, *_RIG_SUB)
        cands = [rbase]
        try:
            cands += [os.path.join(rbase, n) for n in sorted(os.listdir(rbase))
                      if os.path.isdir(os.path.join(rbase, n)) and not re.match(r"^v\d+$", n, re.I)]
        except OSError:
            pass
        for c in cands:
            p2, t2 = _latest(c, _RIG_EXT, cutoff)
            if p2 and t2 >= rt:
                rp, rt = p2, t2
        src_t = max(mt, ct)               # the rig must be at least as new as the newest model / CC file
        if not mp and not cp:
            state = "nomodel"
        elif not rp:
            state = "norig"
        elif rt < src_t:
            state = "old"
        else:
            state = "ok"
        cc_state = "" if not cp else ("old" if (not rp or rt < ct) else "ok")   # CC comes with modeling: red when the rig is older than it
        rows.append({"asset": rel, "type": atype, "model": mp, "model_t": mt, "cc": cp, "cc_t": ct, "cc_state": cc_state,
                     "rig": rp, "rig_t": rt, "state": state})
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
        self.status_when = QtWidgets.QComboBox()
        for label, key in (("Any date", "all"), ("Today", "today"), ("Yesterday", "yesterday"),
                           ("Last 7 days", "7d"), ("Last 30 days (1 month)", "30d"), ("Between dates...", "custom")):
            self.status_when.addItem(label, key)
        self.status_when.setToolTip("Only show assets whose model, CC or rig file was saved in this period")
        bar.addWidget(self.status_when)
        self.status_from = QtWidgets.QDateEdit(QtCore.QDate.currentDate().addDays(-7))
        self.status_to = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        for d in (self.status_from, self.status_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd-MM-yyyy")
            d.setVisible(False)
            bar.addWidget(d)
        self.status_asof = QtWidgets.QCheckBox("Status on date")
        self.status_asof.setToolTip("Show only the assets whose model, CC or rig file was created on the chosen day")
        bar.addWidget(self.status_asof)
        self.status_asof_date = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.status_asof_date.setCalendarPopup(True)
        self.status_asof_date.setDisplayFormat("dd-MM-yyyy")
        self.status_asof_date.setVisible(False)
        bar.addWidget(self.status_asof_date)
        bar.addStretch()
        self.status_only_old = QtWidgets.QCheckBox("Only outdated")
        bar.addWidget(self.status_only_old)
        btn_copy = QtWidgets.QPushButton("Copy table")
        btn_copy.setToolTip("Copy every row currently shown (respects filter / sort) as tab-separated text - paste into Excel, chat or mail")
        btn_copy.setFixedHeight(28)
        bar.addWidget(btn_copy)
        btn_sheet = QtWidgets.QPushButton("Google Sheet")
        btn_sheet.setToolTip("Make the tracker sheet (CH / DRAFT 1 / DRAFT 2 / HAIR-CLOTH / Ready for RIG / RIG STATUS ...) from the rows shown, then open Google Sheets to import it")
        btn_sheet.setFixedHeight(28)
        bar.addWidget(btn_sheet)
        btn_refresh = QtWidgets.QPushButton("Refresh")
        btn_refresh.setToolTip("Re-scan the project folders now")
        btn_refresh.setFixedHeight(28)
        bar.addWidget(btn_refresh)
        lay.addLayout(bar)

        self.status_counts = QtWidgets.QLabel("")
        self.status_counts.setStyleSheet("color: #cccccc; font-size: 12px;")
        lay.addWidget(self.status_counts)

        cols = ["Asset", "Type", "Model version", "Model saved", "CC version", "CC saved", "Rig version", "Rig saved", "Status"]
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

        self.status_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.status_table.customContextMenuRequested.connect(self._status_menu)
        self._status_rows = []
        self._status_fill_projects()
        self.status_project.currentIndexChanged.connect(lambda *_: self.status_refresh())
        self.status_search.textChanged.connect(lambda *_: self._status_render())
        self.status_only_old.toggled.connect(lambda *_: self._status_render())
        self.status_when.currentIndexChanged.connect(self._status_when_changed)
        self.status_from.dateChanged.connect(lambda *_: self._status_render())
        self.status_to.dateChanged.connect(lambda *_: self._status_render())
        btn_refresh.clicked.connect(lambda *_: self.status_refresh())
        btn_copy.clicked.connect(self._status_copy_all)
        btn_sheet.clicked.connect(self._status_google_sheet)
        self.status_asof.toggled.connect(self._status_asof_changed)
        self.status_asof_date.dateChanged.connect(lambda *_: self._status_render())
        return w

    # Ã¢â€â‚¬Ã¢â€â‚¬ data Ã¢â€â‚¬Ã¢â€â‚¬
    def _status_fill_projects(self):
        """Project = kl_assets. The dropdown filters by asset TYPE, taken from the folder under assets
        (characters, props, locations ...). 'All types' scans everything."""
        self.status_project.blockSignals(True)
        self.status_project.clear()
        self.status_project.addItem("kl_assets - all types", "")
        try:
            for n in sorted(os.listdir(DEFAULT_STATUS_ROOT), key=str.lower):
                if not n.startswith(".") and os.path.isdir(os.path.join(DEFAULT_STATUS_ROOT, n)):
                    self.status_project.addItem("kl_assets - " + n, n)
        except OSError:
            pass
        self.status_project.blockSignals(False)

    def _status_asof_changed(self, *_):
        self.status_asof_date.setVisible(self.status_asof.isChecked())
        self._status_render()          # no re-scan: the data is already loaded, only the filter changes

    def _status_google_sheet(self):
        """Build the production-tracker sheet (.xlsx) from the rows shown, then open the folder and Google Sheets:
        drag the file onto the Google Sheets page (or File > Import) - the drop-downs and colours come along."""
        from . import status_sheet
        rows = list(getattr(self, "_status_shown", None) or self._status_rows)
        if not rows:
            cmds.warning("[KRT] Nothing to export - the table is empty.")
            return
        proj = re.sub(r"[^A-Za-z0-9_\-]+", "_", self.status_project.currentText()).strip("_") or "project"
        folder = os.path.join(os.path.expanduser("~"), "Documents", "KRT_Status")
        path = os.path.join(folder, "rig_model_status_%s_%s.xlsx" % (proj, time.strftime("%Y%m%d_%H%M")))
        try:
            status_sheet.write_xlsx(path, rows)
        except Exception as e:
            cmds.warning("[KRT] Could not write the sheet: %s" % e)
            return
        try:
            subprocess.Popen('explorer /select,"%s"' % path.replace("/", "\\"))
        except Exception:
            pass
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://docs.google.com/spreadsheets/u/0/"))
        try:
            import maya.cmds as _c
            _c.inViewMessage(amg="Sheet saved (%d assets). Drag the file onto Google Sheets, or File > Import > Upload" % len(rows),
                             pos="midCenter", fade=True)
        except Exception:
            pass

    def _status_when_changed(self, *_):
        custom = self.status_when.currentData() == "custom"
        self.status_from.setVisible(custom)
        self.status_to.setVisible(custom)
        self._status_render()

    def _status_period(self):
        """-> (start_ts, end_ts) of the chosen period, or None for any date. Local time, end exclusive."""
        if self.status_asof.isChecked():          # one exact day: files created on that date only
            d = self.status_asof_date.date()
            t0 = time.mktime((d.year(), d.month(), d.day(), 0, 0, 0, 0, 0, -1))
            d2 = d.addDays(1)
            return t0, time.mktime((d2.year(), d2.month(), d2.day(), 0, 0, 0, 0, 0, -1))
        key = self.status_when.currentData()
        if key == "all":
            return None
        today = QtCore.QDate.currentDate()

        def ts(d):
            return time.mktime((d.year(), d.month(), d.day(), 0, 0, 0, 0, 0, -1))
        if key == "today":
            a, b = today, today
        elif key == "yesterday":
            a = b = today.addDays(-1)
        elif key == "7d":
            a, b = today.addDays(-6), today
        elif key == "30d":
            a, b = today.addDays(-29), today
        else:
            a, b = self.status_from.date(), self.status_to.date()
            if a > b:
                a, b = b, a
        return ts(a), ts(b.addDays(1))

    def _status_copy_all(self):
        """Copy the table as currently shown (filter + sort applied) as aligned plain text - readable in a .txt file.
        Asset name, type, model / CC / rig version + date and status only; no file paths."""
        t = self.status_table
        heads = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
        rows = []
        for r in range(t.rowCount()):
            rows.append([t.item(r, c).text() if t.item(r, c) else "" for c in range(t.columnCount())])
        widths = [max([len(heads[c])] + [len(x[c]) for x in rows]) for c in range(len(heads))]

        def line(cells):
            return "  ".join(cells[c].ljust(widths[c]) for c in range(len(cells))).rstrip()
        out = ["RIG & MODEL STATUS - %s - %s" % (self.status_project.currentText(), time.strftime("%d-%m-%Y %H:%M")),
               line(heads), "  ".join("-" * w for w in widths)]
        out += [line(x) for x in rows]
        QtWidgets.QApplication.clipboard().setText("\n".join(out))
        try:
            import maya.cmds as _c
            _c.inViewMessage(amg="Copied %d rows" % len(rows), pos="midCenter", fade=True)
        except Exception:
            pass

    def _status_menu(self, pos):
        """Right-click a row: copy the model / CC / rig path (or open its folder). Read only - nothing is changed."""
        t = self.status_table
        it = t.itemAt(pos)
        if it is None:
            return
        asset, atype = t.item(it.row(), 0).text(), t.item(it.row(), 1).text()
        r = next((x for x in self._status_rows if x["asset"] == asset and x["type"] == atype), None)
        if not r:
            return
        menu = QtWidgets.QMenu(self)
        acts = {}
        for key, name in (("model", "model"), ("cc", "CC"), ("rig", "rig")):
            a = menu.addAction("Copy %s path" % name)
            a.setEnabled(bool(r[key]))
            acts[a] = ("copy", r[key])
        menu.addSeparator()
        for key, name in (("model", "model"), ("cc", "CC"), ("rig", "rig")):
            a = menu.addAction("Open %s folder" % name)
            a.setEnabled(bool(r[key]))
            acts[a] = ("open", r[key])
        col = t.currentColumn()
        key = {2: "model", 3: "model", 4: "cc", 5: "cc", 6: "rig", 7: "rig"}.get(col, "")
        a = menu.addAction("Copy this cell's path")
        a.setEnabled(bool(key))
        acts[a] = ("copy", r.get(key, "") if key else "")
        gp = t.viewport().mapToGlobal(pos)
        try:
            ch = menu.exec(gp)
        except AttributeError:
            ch = menu.exec_(gp)
        if ch in acts:
            kind, p = acts[ch]
            if not p:
                return
            if kind == "copy":
                QtWidgets.QApplication.clipboard().setText(p.replace("\\", "/"))
            else:
                try:
                    os.startfile(os.path.dirname(p))
                except Exception:
                    pass

    def status_refresh(self):
        cat = self.status_project.currentData() or ""
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            rows = scan_project(DEFAULT_STATUS_ROOT)
            self._status_rows = [r for r in rows if not cat or r["type"] == cat]
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._status_render()

    def _status_render(self):
        QT = QtCore.Qt
        rows = self._status_rows
        per = self._status_period()
        if per:
            rows = [r for r in rows if any(per[0] <= t < per[1] for t in (r["model_t"], r["cc_t"], r["rig_t"]) if t)]
        total = len(rows)
        n_model = sum(1 for r in rows if r["model"] or r["cc"])
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
        shown = [r for r in rows if (not flt or flt in (r["asset"] + " " + r["type"]).lower())
                 and (not only_old or r["state"] in ("old", "norig"))]
        self._status_shown = shown
        t = self.status_table
        t.setSortingEnabled(False)
        t.setRowCount(len(shown))
        label = {"ok": "Up to date", "old": "Rig older than model", "norig": "No rig", "nomodel": "No model"}
        for i, r in enumerate(shown):
            col = {"ok": _GREEN, "old": _RED, "norig": _RED}.get(r["state"], _GREY)
            tint = QtGui.QColor(col)
            tint.setAlpha(34)
            vals = [r["asset"], r["type"], _ver(r["model"]) or ("-" if not r["model"] else "?"), _fmt(r["model_t"]),
                    _ver(r["cc"]) or ("-" if not r["cc"] else "?"), _fmt(r["cc_t"]),
                    _ver(r["rig"]) or ("-" if not r["rig"] else "?"), _fmt(r["rig_t"]), label[r["state"]]]
            tips = ["", "", r["model"], r["model"], r["cc"], r["cc"], r["rig"], r["rig"], ""]
            cc_col = {"ok": _GREEN, "old": _RED}.get(r["cc_state"], _GREY)
            for c, v in enumerate(vals):
                it = QtWidgets.QTableWidgetItem(v)
                it.setToolTip(tips[c])
                it.setBackground(tint)
                if c == 1:
                    tc = QtGui.QColor(_TYPE_COLORS.get(r["type"].lower(), _TYPE_OTHER))
                    bg = QtGui.QColor(tc)
                    bg.setAlpha(70)
                    it.setBackground(bg)
                    it.setForeground(tc)
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setTextAlignment(QtCore.Qt.AlignCenter)
                elif c in (4, 5):
                    it.setForeground(QtGui.QColor(cc_col))
                elif c == 0 or c >= 6:
                    it.setForeground(QtGui.QColor(col))
                t.setItem(i, c, it)
        t.setSortingEnabled(True)
        t.resizeColumnsToContents()
