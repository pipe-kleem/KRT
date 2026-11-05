"""Run a step list in order, stopping at the first failure (Stage 61).

Used by every "steps" panel module (joint_transfer, finger_fix). A module
defines STEPS = [(key, label), ...] and a runner(key, **opts)."""
import time
import traceback


def run_steps(steps, runner, keys=None, on_step=None, opts=None, log=print):
    """Returns (success, error_text). on_step(key, 'running'|'ok'|'error')."""
    keys = [k for k, _ in steps if keys is None or k in keys]
    t0 = time.time()
    for key in keys:
        if on_step:
            on_step(key, "running")
        try:
            runner(key, **(opts or {}))
        except Exception:
            err = "Step '{}' failed:\n{}".format(key, traceback.format_exc())
            log(err)
            if on_step:
                on_step(key, "error")
            return False, err
        if on_step:
            on_step(key, "ok")
    log("{} step(s) done in {:.1f}s".format(len(keys), time.time() - t0))
    return True, ""
