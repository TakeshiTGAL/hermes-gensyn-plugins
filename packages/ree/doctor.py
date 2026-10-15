from __future__ import annotations
import json
import os
import platform
import shutil
from pathlib import Path
if __package__:
    from .contract import IMAGE_DIGEST, IMAGE_REF, image_absent_message
    from .docker import ENV_ALLOWLIST, child_env, leftover_rows
    from .capacity import context_setting
    from .process import ChildError, run_child
else:
    from contract import IMAGE_DIGEST, IMAGE_REF, image_absent_message
    from docker import ENV_ALLOWLIST, child_env, leftover_rows
    from capacity import context_setting
    from process import ChildError, run_child
_LOW_DISK = 2 * 1024 * 1024 * 1024
def _argv(context, args):
    if context: return ["docker", "--context", context, *args]
    return ["docker", *args]
def _check(status, message, **details):
    return {"status": status, "message": message, **details}
def _run(runner, argv):
    env = {key: os.environ[key] for key in ENV_ALLOWLIST if os.environ.get(key)} or child_env()
    try: return runner(argv, b"", env, 15)
    except ChildError as exc: return exc
def run_doctor(*, runner=run_child):
    checks = {}
    context = context_setting()
    found = shutil.which("docker")
    checks["docker"] = _check(
        "ok" if found else "error", "Docker is on PATH." if found else "Docker was not found.",
    )
    daemon = _run(runner, _argv(context, ["version", "--format", "{{.Server.Version}}"]))
    down = isinstance(daemon, ChildError) or daemon.returncode != 0
    if down:
        checks["daemon"] = _check("error", "Docker daemon is not reachable.")
        checks["image"] = _check("error", "Image was not checked because the Docker daemon is not reachable.")
    else:
        checks["daemon"] = _check("ok", "Docker daemon answered.")
        image = _run(runner, _argv(context, [
            "image", "inspect", IMAGE_REF, "--format", "{{.Id}} {{json .RepoDigests}}",
        ]))
        stdout = b"" if isinstance(image, ChildError) else image.stdout
        code = 1 if isinstance(image, ChildError) else image.returncode
        missing = code != 0 or IMAGE_DIGEST.encode() not in stdout
        if missing: checks["image"] = _check("error", image_absent_message())
        else: checks["image"] = _check("ok", "Pinned image is local.", digest=IMAGE_DIGEST)
    checks["cpu"] = _check("ok", "CPU only in this version.", machine=platform.machine())
    home = os.environ.get("HOME", "")
    if not home: checks["cache"] = _check("error", "HOME is unset, so cache paths are unknown.")
    else:
        root = Path(home).expanduser() / ".cache"
        free = shutil.disk_usage(root if root.exists() else Path(home)).free
        checks["cache"] = _check(
            "warn" if free < _LOW_DISK else "ok",
            "Weights use ~/.cache/gensyn and ~/.cache/huggingface.", free_bytes=free,
        )
    rows = leftover_rows(context)
    if rows:
        running = any(row["state"] == "running" for row in rows)
        if running: message = "Named containers are still running."
        else: message = "Named containers are left behind and are not running."
        if context: message += " On context " + context + "."
        checks["leftovers"] = _check(
            "warn", message, names=[row["name"] for row in rows], states=[row["state"] for row in rows],
            context=context or "current",
        )
    statuses = [item["status"] for item in checks.values()]
    checks["overall"] = "error" if "error" in statuses else "warn" if "warn" in statuses else "healthy"
    return checks
def doctor_main(_args=None):
    report = run_doctor()
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["overall"] == "healthy" else 1
