"""One file dialog for all of KRT (Stage 65).

Drop-in for cmds.fileDialog2: same flags (fm/fileMode, ff/fileFilter,
dir/startingDirectory, caption), same return (list of paths or None), but it
opens Qt's standard OS dialog. Maya's own fileDialog2 sometimes opened
empty - no folders, no files - inside KRT's panels; the OS dialog always
lists the folder.

    fileMode 0 = save (any file), 1 = one existing file,
             2 = any name, 3 = directory, 4 = several existing files
"""
import os

from ..compat import QtWidgets


def _start(path):
    """A folder or file that exists, or the nearest existing parent, or ''."""
    path = (path or "").replace("\\", "/")
    while path and not os.path.exists(path):
        parent = os.path.dirname(path.rstrip("/"))
        if parent == path:
            return ""
        path = parent
    return path


def file_dialog2(**kw):
    mode = kw.get("fileMode", kw.get("fm", 0))
    filt = kw.get("fileFilter", kw.get("ff", "")) or "All Files (*.*)"
    caption = kw.get("caption", kw.get("cap", "")) or "Select"
    wanted = kw.get("startingDirectory", kw.get("dir", "")) or ""
    parent = QtWidgets.QApplication.activeWindow()
    qfd = QtWidgets.QFileDialog

    if mode == 3:
        res = qfd.getExistingDirectory(parent, caption, _start(wanted))
        return [res.replace("\\", "/")] if res else None
    if mode == 0:
        # a save path that doesn't exist yet is fine: Qt pre-fills its name
        start = wanted if os.path.isdir(os.path.dirname(wanted) or ".") else _start(wanted)
        res = qfd.getSaveFileName(parent, caption, start, filt)[0]
        return [res.replace("\\", "/")] if res else None
    if mode == 4:
        res = qfd.getOpenFileNames(parent, caption, _start(wanted), filt)[0]
        return [r.replace("\\", "/") for r in res] or None
    res = qfd.getOpenFileName(parent, caption, _start(wanted), filt)[0]
    return [res.replace("\\", "/")] if res else None
