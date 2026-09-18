"""Auto-split from utils.py."""
from ._shared import *


######################################
# Crash logging / last-session recovery (Stage 16)
#
# Two independent signals, both read once at launch by
# check_last_session_health() and then combined by main.py into one
# "here's what happened last time" popup:
#
#   1. An actual logged error - anything KRT's own top-level exception
#      handlers (tool launch, a rig build batch, a custom script) caught
#      and passed to log_crash(). This is the specific, readable case:
#      "here's exactly what went wrong."
#   2. An unclean exit - a small marker file written at the START of every
#      run (mark_session_start) and only ever removed at a NORMAL close
#      (mark_session_clean_exit, from KRT_Tool.closeEvent). If that marker
#      is still there the next time KRT opens, the previous run never
#      reached a normal close - almost always Maya itself going down
#      (a hard crash), since a plain Python exception inside KRT still
#      leaves the window open to be closed normally afterward.
#
# Neither of these can catch a true native crash while it happens (nothing
# running inside the process can log after Maya itself dies) - the marker
# file is what stands in for that case, at the cost of only being able to
# say "something ended badly", not why.
######################################

def _krt_log_dir():
    base = os.path.join(cmds.internalVar(userAppDir=True), "KRT").replace("\\", "/")
    if not os.path.exists(base):
        try:
            os.makedirs(base)
        except Exception:
            pass
    return base


def _crash_log_path():
    return os.path.join(_krt_log_dir(), "crash_log.txt")


def _session_marker_path():
    return os.path.join(_krt_log_dir(), "session_active.json")


def log_crash(context, exc=None, extra=""):
    """Append one timestamped entry to KRT's crash log. Call this from
    KRT's own top-level exception handlers - tool launch (main.py),
    a module/rig build batch (widgets.py), custom script execution
    (workspace.py) - anywhere an error is already being caught and shown
    in KRT's own UI, so it's ALSO durably saved for
    check_last_session_health() to surface next time KRT opens. Never
    raises itself - a failure to log must never mask the original error,
    so any problem writing the log file is just swallowed."""
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = ["=" * 70, "[{}] {}".format(ts, context)]
        if exc is not None:
            lines.append("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip())
        elif extra:
            lines.append(str(extra).rstrip())
        lines.append("")
        with open(_crash_log_path(), "a") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass


def mark_session_start():
    """Call once, right as KRT starts opening (before anything risky runs).
    See the module-level note above for how this pairs with
    mark_session_clean_exit()/check_last_session_health()."""
    try:
        with open(_session_marker_path(), "w") as f:
            json.dump({"started_readable": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    except Exception:
        pass


def mark_session_clean_exit():
    """Call from KRT_Tool.closeEvent - a normal close, so the marker
    mark_session_start() wrote no longer means anything and shouldn't be
    reported as a crash next launch."""
    try:
        p = _session_marker_path()
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass


def check_last_session_health():
    """Call once, right when KRT opens, BEFORE mark_session_start()
    overwrites the marker for this new run. Reads (and, for the crash log,
    CONSUMES - clears it after reading) whatever the previous run left
    behind, so the same old error only ever gets reported once.

    Returns {"unclean_exit": bool, "started_readable": str_or_None,
    "last_error": str_or_None}."""
    result = {"unclean_exit": False, "started_readable": None, "last_error": None}

    marker = _session_marker_path()
    if os.path.exists(marker):
        result["unclean_exit"] = True
        try:
            with open(marker, "r") as f:
                result["started_readable"] = json.load(f).get("started_readable")
        except Exception:
            pass

    log_path = _crash_log_path()
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                content = f.read()
            blocks = [b.strip() for b in content.split("=" * 70) if b.strip()]
            if blocks:
                result["last_error"] = blocks[-1]
        except Exception:
            pass
        finally:
            try:
                os.remove(log_path)
            except Exception:
                pass

    return result
