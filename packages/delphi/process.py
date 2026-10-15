"""The only subprocess boundary used by tools and doctor."""
from __future__ import annotations
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
REQUEST_LIMIT = 65_536
STDOUT_LIMIT = 262_144
STDERR_LIMIT = 262_144
class ChildError(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind
@dataclass(frozen=True)
class ChildResult:
    returncode: int
    stdout: bytes
    stderr: bytes
def _stop_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is not None and not stream.closed:
            stream.close()
    try:
        proc.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
def run_child(argv, request, env, deadline, cwd=None):
    """Run one child with bounded stdio and one monotonic deadline."""
    if not isinstance(request, bytes) or len(request) > REQUEST_LIMIT:
        raise ChildError("invalid_argument", "Child request is too large.")
    if deadline <= 0:
        raise ChildError("timeout", "Child deadline expired.")
    child_env = {str(key): str(value) for key, value in env.items()}
    child_env["LC_ALL"] = "C"
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            list(argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False, env=child_env,
            start_new_session=True, cwd=cwd, bufsize=0,
        )
    except (OSError, ValueError) as exc:
        raise ChildError("config", f"Could not start child: {type(exc).__name__}.") from None
    selector = selectors.DefaultSelector()
    output = bytearray()
    errors = bytearray()
    sent = 0
    try:
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            os.set_blocking(stream.fileno(), False)
        if request:
            selector.register(proc.stdin, selectors.EVENT_WRITE, "stdin")
        else:
            proc.stdin.close()
        selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map():
            remaining = deadline - (time.monotonic() - started)
            if remaining <= 0:
                raise ChildError("timeout", "Child deadline expired.")
            events = selector.select(remaining)
            if not events:
                raise ChildError("timeout", "Child deadline expired.")
            for key, _ in events:
                stream = key.fileobj
                if key.data == "stdin":
                    try:
                        count = os.write(stream.fileno(), request[sent : sent + 65_536])
                    except BrokenPipeError:
                        count = 0
                    sent += count
                    if sent >= len(request) or count == 0:
                        selector.unregister(stream)
                        stream.close()
                    continue
                try:
                    chunk = os.read(stream.fileno(), 65_536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                target = output if key.data == "stdout" else errors
                target.extend(chunk)
                limit = STDOUT_LIMIT if key.data == "stdout" else STDERR_LIMIT
                if len(target) > limit:
                    raise ChildError("invalid_response", f"Child {key.data} is too large.")
        remaining = deadline - (time.monotonic() - started)
        if remaining <= 0:
            raise ChildError("timeout", "Child deadline expired.")
        try:
            returncode = proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise ChildError("timeout", "Child deadline expired.") from None
        return ChildResult(returncode, bytes(output), bytes(errors))
    except ChildError:
        _stop_group(proc)
        raise
    except Exception:
        _stop_group(proc)
        raise
    finally:
        selector.close()
