from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sources():
    return [path for path in ROOT.glob("*.py")]


def test_forbidden_shapes_are_absent():
    text = "\n".join(path.read_text() for path in sources())
    assert "shell=True" not in text
    assert "os.system" not in text
    assert "os.popen" not in text
    assert "post_tool_call" not in text
    assert "HF_TOKEN" not in text
    assert "privileged" not in text
    assert "docker.sock" not in text
    assert "--gpus" not in text
    assert "from delphi" not in text
    assert "import delphi" not in text
    assert "from shared" not in text
    assert re.search(r"""['\"]pull['\"]""", text) is None
    assert re.search(r"""['\"]save['\"]|['\"]export['\"]|['\"]cp['\"]""", text) is None
    assert "parse_float=float" not in text
    assert "os.environ.copy()" not in text
    subprocesses = [
        path for path in sources()
        if re.search(r"^\s*(import subprocess|from subprocess)", path.read_text(), re.M)
    ]
    assert [path.name for path in subprocesses] == ["process.py"]
