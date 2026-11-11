"""Run the two plugin suites in separate processes when both would load together.

Each plugin imports top-level modules such as ``service``. One interpreter
cannot hold both. ``pytest`` at this repo, and ``pytest packages/delphi
packages/ree``, start one child per plugin. A run of a single plugin is unchanged.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_CHILD = "GENSYN_PYTEST_CHILD"


def _named(args, folder):
    needle = folder.replace("\\", "/")
    for arg in args:
        text = str(arg).replace("\\", "/")
        if text == needle or text.endswith("/" + needle) or needle + "/" in text:
            return True
    return False


def pytest_cmdline_main(config):
    if os.environ.get(_CHILD):
        return None
    args = [str(arg) for arg in config.args]
    delphi = _named(args, "packages/delphi")
    ree = _named(args, "packages/ree")
    if delphi != ree:
        return None
    env = os.environ.copy()
    env[_CHILD] = "1"
    forwarded = []
    args = [str(arg) for arg in config.invocation_params.args]
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "-p" and index + 1 < len(args):
            forwarded.extend([arg, args[index + 1]])
            index += 2
            continue
        if arg.startswith("-p"):
            forwarded.append(arg)
        index += 1
    code = 0
    for folder in ("packages/delphi", "packages/ree"):
        result = subprocess.call(
            [sys.executable, "-m", "pytest", "-q", *forwarded, folder],
            cwd=ROOT,
            env=env,
        )
        if result:
            code = result
    return code
