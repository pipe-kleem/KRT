"""
╔══════════════════════════════════════════════════════════╗
║                KRT — DRAG & DROP INSTALLER                ║
║                                                          ║
║  HOW TO USE:                                             ║
║  1. Open Maya                                            ║
║  2. Drag this file into the Maya viewport                ║
║  3. Done! A 'KRT' shelf button AND a 'KRT' menu in the   ║
║     top menu bar are created. The menu is also rebuilt   ║
║     automatically every time Maya starts.                ║
╚══════════════════════════════════════════════════════════╝
"""

PACKAGE_NAME = "KRT"
SHELF_NAME = "KRT"


# ── Maya drag-and-drop entry point ───────────────────────────────────────────
def onMayaDroppedPythonFile(*args, **kwargs):
    """Called automatically by Maya when this file is dragged into the viewport."""
    _run_installer()


def _run_installer():
    import sys
    import os
    import shutil
    import maya.cmds as cmds

    # ── 1. Locate the package folder (this installer sits inside it) ──────────
    installer_dir = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
    package_src = installer_dir

    # ── 2. Destination = Maya's user scripts folder / KRT ────────────────────
    user_scripts = cmds.internalVar(userScriptDir=True).replace("\\", "/").rstrip("/")
    install_dest = os.path.join(user_scripts, PACKAGE_NAME).replace("\\", "/")

    # ── 3. Copy / update the package (skip caches + junk) ────────────────────
    # NOTE: version-control / cache folders (.git, .github, __pycache__) are
    # skipped entirely - their contents are not needed at the install location
    # and git objects are read-only, which used to abort the whole install with
    # "Permission denied". The copy is done file-by-file and is tolerant of any
    # single locked file so a leftover read-only tree can never block an update.
    try:
        src_path = os.path.normcase(os.path.normpath(package_src))
        dst_path = os.path.normcase(os.path.normpath(install_dest))
        if src_path != dst_path:
            # Clean reinstall: close any running KRT window (it holds module
            # references), wipe the old install completely, then copy fresh.
            _close_running_krt()
            leftover = _wipe_tree(install_dest)
            if leftover:
                cmds.warning(f"[KRT] {leftover} old file(s) could not be deleted (locked) - they will be overwritten.")
            copied, skipped = _safe_copy_tree(package_src, install_dest)
            removed = _remove_stale_modules(package_src, install_dest)
            if removed:
                cmds.warning("[KRT] Removed stale module(s) from install: " + ", ".join(removed))
            if copied == 0:
                cmds.error("[KRT] Nothing was copied - check folder permissions.")
                return
            msg = f"[KRT] Package installed -> {install_dest} ({copied} file(s))"
            if skipped:
                msg += f"; {skipped} locked file(s) skipped (safe to ignore)"
            cmds.warning(msg)
        else:
            cmds.warning("[KRT] Running directly from scripts folder. Skipping copy.")
    except Exception as e:
        cmds.error(f"[KRT] Failed to copy package: {e}")
        return

    # ── 4. Make sure the scripts folder is importable ────────────────────────
    # Put the install folder FIRST - if another 'KRT' folder sits earlier on
    # sys.path (an old copy elsewhere), 'import KRT' would silently load that
    # one and the drag-drop would look like it "didn't update".
    while user_scripts in sys.path:
        sys.path.remove(user_scripts)
    sys.path.insert(0, user_scripts)

    # ── 5. Flush any stale copies already in memory ──────────────────────────
    for m in [x for x in list(sys.modules) if x == PACKAGE_NAME or x.startswith(PACKAGE_NAME + ".")]:
        del sys.modules[m]

    # ── 6. Smoke-test the import ─────────────────────────────────────────────
    try:
        import importlib
        importlib.invalidate_caches()
        pkg = importlib.import_module(PACKAGE_NAME)
        loaded_from = os.path.dirname(os.path.abspath(pkg.__file__)).replace("\\", "/")
        if os.path.normcase(loaded_from) != os.path.normcase(install_dest):
            cmds.warning(f"[KRT] WARNING: 'import KRT' loaded from {loaded_from}, NOT the fresh install at {install_dest}. "
                         "Remove/rename that other KRT folder (or its sys.path entry in userSetup.py) so updates take effect.")
        else:
            cmds.warning(f"[KRT] Package imported successfully from {loaded_from}")
    except Exception as e:
        cmds.error(f"[KRT] Import test failed: {e}")
        return

    # ── 7. Shelf button + top menu + startup hook ────────────────────────────
    # _create_shelf() is defensive internally (see its docstring) but is
    # ALSO wrapped here: a shelf-tab hiccup (Maya's own addNewShelfTab MEL
    # proc erroring - reported as "Object's name 'spacingSeparator' is not
    # unique") used to raise straight out of this function with nothing
    # caught, which aborted the entire installer before the KRT menu or the
    # startup hook ever ran. A missing shelf button is cosmetic - a missing
    # menu/startup hook means the tool can't be launched at all - so this
    # step must never be allowed to take the rest of the install down with it.
    try:
        _create_shelf()
    except Exception as e:
        cmds.warning(
            f"[KRT] Could not create the shelf button: {e} "
            f"(the KRT menu below still works to launch the tool)."
        )
    try:
        import KRT.menu as krt_menu
        krt_menu.build_menu()
        cmds.warning("[KRT] Top menu created.")
    except Exception as e:
        cmds.warning(f"[KRT] Could not build menu: {e}")
    _install_startup_hook(user_scripts)

    # ── 8. Offer to launch now ───────────────────────────────────────────────
    choice = cmds.confirmDialog(
        title="KRT — Installed!",
        message=(
            "✅  Installation complete!\n\n"
            f"Package location:\n{install_dest}\n\n"
            "Added: a 'KRT' shelf button and a 'KRT' menu in the top menu bar\n"
            "(the menu is rebuilt automatically on Maya startup).\n\n"
            "Launch the tool now?"
        ),
        button=["Launch Now", "Close"],
        defaultButton="Launch Now",
        cancelButton="Close",
        dismissString="Close",
    )
    if choice == "Launch Now":
        try:
            import KRT.menu as krt_menu
            krt_menu.launch()
        except Exception as e:
            cmds.error(f"[KRT] Launch failed: {e}")


# Folder / file names that must never be copied to the install destination.
_SKIP_DIRS = {".git", ".github", "__pycache__", "tools", "archive", "Claude outputs"}
_SKIP_FILE_EXT = {".pyc", ".pyo", ".md"}
_SKIP_FILE_NAMES = {"_t.txt", "_cache_write_test.txt"}


def _safe_copy_tree(src, dst):
    """Copy every file from src to dst, skipping version-control/cache folders
    and tolerating individual locked/read-only files instead of aborting.
    Returns (copied_count, skipped_count)."""
    import os
    import stat
    import shutil

    copied = 0
    skipped = 0
    for dirpath, dirnames, filenames in os.walk(src):
        # Prune skipped folders in-place so os.walk does not descend into them.
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        rel = os.path.relpath(dirpath, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception:
            skipped += len(filenames)
            continue

        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in _SKIP_FILE_EXT or name in _SKIP_FILE_NAMES or name.endswith(".tmp"):
                continue
            s = os.path.join(dirpath, name)
            d = os.path.join(target_dir, name)
            try:
                # Clear a read-only flag on any existing target so it can be overwritten.
                if os.path.exists(d):
                    try: os.chmod(d, stat.S_IWRITE)
                    except Exception: pass
                shutil.copy2(s, d)
                copied += 1
            except Exception:
                skipped += 1
    return copied, skipped


def _close_running_krt():
    """Close an open KRT window so its modules can be dropped and replaced."""
    try:
        from PySide6 import QtWidgets
    except ImportError:
        try:
            from PySide2 import QtWidgets
        except ImportError:
            return
    try:
        for w in QtWidgets.QApplication.topLevelWidgets():
            if w.objectName() == "KRT_Window":
                w.close(); w.deleteLater()
    except Exception:
        pass


def _wipe_tree(dst):
    """Delete everything under dst (files first, then empty dirs). Locked
    files are skipped and counted; the copy afterwards overwrites them."""
    import os, stat
    if not os.path.isdir(dst):
        return 0
    leftover = 0
    for dirpath, dirnames, filenames in os.walk(dst, topdown=False):
        for n in filenames:
            p = os.path.join(dirpath, n)
            try:
                os.chmod(p, stat.S_IWRITE); os.remove(p)
            except Exception:
                leftover += 1
        for d in dirnames:
            try: os.rmdir(os.path.join(dirpath, d))
            except Exception: pass
    return leftover


def _remove_stale_modules(src, dst):
    """Delete top-level *.py files in dst that have no counterpart in src
    (e.g. graph.py after graph/ became a package). Returns removed names."""
    import os
    removed = []
    try:
        src_files = {n for n in os.listdir(src) if n.lower().endswith(".py")}
        for n in os.listdir(dst):
            full = os.path.join(dst, n)
            if n.lower().endswith(".py") and os.path.isfile(full) and n not in src_files:
                try:
                    os.remove(full)
                    removed.append(n)
                except Exception:
                    pass
    except Exception:
        pass
    return removed


# ── Launch command used by the shelf button (python sourceType) ──────────────
_LAUNCH_CMD = "import KRT.menu as _krt; _krt.launch()"


def _create_shelf():
    """Create (or replace) the 'KRT' shelf with a launch button.

    Tolerant of a known Maya quirk where its own addNewShelfTab.mel errors
    with "Object's name 'spacingSeparator' is not unique." - a leftover
    'spacingSeparator' UI control from a shelf tab that never got fully torn
    down (e.g. a stale shelf_KRT.mel prefs file Maya reloaded on startup
    before this installer ran, so the childArray check below never saw it
    as "existing" and skipped deleteShelfTab). That stray control is
    cleaned up before asking Maya to add a fresh tab, and if addNewShelfTab
    still errors, the shelf tab is built directly with cmds.shelfLayout
    instead - which never touches that decorative separator at all - so a
    shelf-tab hiccup can't stop the button from ending up somewhere usable.
    """
    import maya.cmds as cmds
    import maya.mel as mel

    shelf_top = mel.eval("$tmp = $gShelfTopLevel")
    existing = cmds.tabLayout(shelf_top, query=True, childArray=True) or []
    if SHELF_NAME in existing:
        try:
            mel.eval(f'deleteShelfTab "{SHELF_NAME}"')
        except Exception:
            pass

    try:
        if cmds.control("spacingSeparator", exists=True):
            cmds.deleteUI("spacingSeparator", control=True)
    except Exception:
        pass

    shelf_ok = False
    try:
        mel.eval(f'addNewShelfTab "{SHELF_NAME}"')
        shelf_ok = True
    except Exception as e:
        cmds.warning(
            f"[KRT] addNewShelfTab reported an error ({e}) - "
            f"falling back to a direct shelf tab."
        )

    if not shelf_ok or not cmds.control(SHELF_NAME, exists=True):
        # Bypass addNewShelfTab's own MEL entirely - just the tab layout
        # KRT's button actually needs to parent to.
        cmds.shelfLayout(SHELF_NAME, parent=shelf_top)

    cmds.shelfButton(
        label="KRT",
        annotation="Launch the KRT Procedural Rig Builder",
        command=_LAUNCH_CMD,
        sourceType="python",
        parent=SHELF_NAME,
        image="commandButton.png",
        imageOverlayLabel="KRT",
        overlayLabelColor=(1, 0.85, 0.85),
        overlayLabelBackColor=(0.17, 0.11, 0.11, 0.6),
        backgroundColor=(0.42, 0.27, 0.27),
    )
    cmds.tabLayout(shelf_top, edit=True, selectTab=SHELF_NAME)
    cmds.warning(f"[KRT] Shelf '{SHELF_NAME}' created.")


# ── Persist the top menu across Maya sessions via userSetup.py ───────────────
_HOOK_START = "# >>> KRT auto-menu >>>"
_HOOK_END = "# <<< KRT auto-menu <<<"
_HOOK_BODY = """\
# >>> KRT auto-menu >>>
try:
    import maya.utils as _krt_mu
    def _krt_boot():
        try:
            import KRT.menu as _krt_menu
            _krt_menu.build_menu()
        except Exception:
            pass
    _krt_mu.executeDeferred(_krt_boot)
except Exception:
    pass
# <<< KRT auto-menu <<<
"""


def _install_startup_hook(user_scripts):
    """Append (or refresh) a guarded block in userSetup.py that rebuilds the KRT
    menu on every Maya launch. Existing userSetup content is preserved."""
    import os
    import maya.cmds as cmds

    setup_path = os.path.join(user_scripts, "userSetup.py").replace("\\", "/")
    try:
        existing = ""
        if os.path.isfile(setup_path):
            with open(setup_path, "r", encoding="utf-8") as f:
                existing = f.read()
        # Strip any previous KRT block so we never stack duplicates.
        if _HOOK_START in existing and _HOOK_END in existing:
            pre = existing.split(_HOOK_START)[0].rstrip()
            post = existing.split(_HOOK_END)[1].lstrip("\n")
            existing = (pre + "\n" + post).strip()
        new_content = (existing + "\n\n" + _HOOK_BODY) if existing.strip() else _HOOK_BODY
        with open(setup_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        cmds.warning(f"[KRT] Startup hook written -> {setup_path}")
    except Exception as e:
        cmds.warning(f"[KRT] Could not write startup hook: {e}")


# ── Standalone / accidental-run guard ────────────────────────────────────────
if __name__ == "__main__":
    print(__doc__)
