"""Changelog window - reads KRT/changelog.py."""
from ._shared import *
from .. import __version__, __build__


class ChangelogDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(ChangelogDialog, self).__init__(parent)
        self.setWindowTitle("KRT Changelog")
        self.resize(640, 520)
        lay = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QLabel("Running KRT %s  (build %s)" % (__version__, __build__))
        head.setStyleSheet("font-weight: bold; color: #2bb5a8; font-size: 13px;")
        lay.addWidget(head)
        view = QtWidgets.QTextBrowser()
        view.setStyleSheet("background: #1e1e1e; color: #ddd; border: 1px solid #444;")
        view.setHtml(self._html())
        lay.addWidget(view)
        btn = QtWidgets.QPushButton("Close")
        btn.clicked.connect(self.accept)
        lay.addWidget(btn)

    @staticmethod
    def _html():
        import importlib
        from .. import changelog
        importlib.reload(changelog)   # so edits show without restarting KRT
        out = []
        for e in changelog.ENTRIES:
            items = "".join("<li>%s</li>" % c for c in e.get("changes", []))
            out.append("<h3 style='color:#2bb5a8'>v%s <span style='color:#888;font-weight:normal'>"
                       "&nbsp;%s</span></h3><ul>%s</ul>" % (e["version"], e["date"], items))
        return "".join(out)
