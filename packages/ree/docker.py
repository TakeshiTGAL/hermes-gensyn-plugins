from __future__ import annotations
import os
import secrets
import shutil
import tempfile
from pathlib import Path
if __package__:
    from .contract import IMAGE_DIGEST, IMAGE_REF, image_absent_message
    from .process import ChildError, run_child
else:
    from contract import IMAGE_DIGEST, IMAGE_REF, image_absent_message
    from process import ChildError, run_child
ENV_ALLOWLIST = ("PATH", "HOME", "TMPDIR", "LANG", "DOCKER_HOST")
class DockerError(Exception):
    def __init__(self, kind, message, cleaned_on="", container="", removed=False):
        super().__init__(message)
        self.kind, self.cleaned_on, self.container, self.removed = kind, cleaned_on, container, removed
def container_name():
    return "gensyn-ree-" + secrets.token_hex(4)
def child_env():
    return {key: os.environ[key] for key in ENV_ALLOWLIST if os.environ.get(key)}
def option_problem(value):
    if not isinstance(value, str) or not value: return "must not be empty"
    if value.startswith("-"): return "must not start with '-'"
    if "\n" in value or "\r" in value: return "must not contain a newline"
    if "\x00" in value: return "must not contain a NUL"
    return None
def _cache_root():
    home = os.environ.get("HOME", "")
    if option_problem(home): raise DockerError(
            "config", "HOME is missing or unsafe, so no container was started.")
    return Path(home).expanduser() / ".cache"
def _mkdir(path):
    missing, cursor = [], path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    try:
        path.mkdir(parents=True, exist_ok=True)
        for item in missing: item.chmod(0o700)
    except OSError: raise DockerError("config", "Cache directory could not be created.") from None
    return path
CACHE_NAMES = ("gensyn", "huggingface")
def cache_dirs():
    root = _cache_root()
    made = []
    for name in CACHE_NAMES:
        path = root / name
        if path.is_symlink(): raise DockerError(
                "config", "A cache path is a symbolic link, so no container was started.",
            )
        made.append(_mkdir(path))
    return made[0], made[1]
def receipt_dir():
    return _mkdir(_cache_root() / "hermes-ree" / "receipts")
def _safe_text(value, label):
    problem = option_problem(value)
    if problem: raise DockerError("invalid_argument", f"{label} {problem}.")
    return value
def _host_path(path):
    text = str(path)
    if option_problem(text): raise DockerError(
            "invalid_argument", "A mount path was unsafe, so no container was started.")
    return text
def _head(context=""):
    return ["docker", "--context", context] if context else ["docker"]
def _base(name, cidfile, context=""):
    return _head(context) + [
        "run", "--rm", "--name", name, "--cidfile", _host_path(cidfile), "--pull", "never",
    ]
def _caches():
    gensyn, huggingface = cache_dirs()
    return [
        "-v", _host_path(gensyn) + ":/home/gensyn/.cache/gensyn",
        "-v", _host_path(huggingface) + ":/home/gensyn/.cache/huggingface",
    ]
def make_cidfile(): return _workdir() / ("cid-" + secrets.token_hex(4))
def validate_argv(name, receipt_file, cidfile):
    mounted = _host_path(receipt_file) + ":/mnt/receipt/receipt.json:ro"
    return _base(name, cidfile) + [
        "--network", "none", "-v", mounted, IMAGE_REF,
        "validate", "--receipt-path", "/mnt/receipt/receipt.json",
    ]
def _cpu(argv, _cpu_only):
    argv.append("--cpu-only")
    return argv
def verify_argv(name, receipt_file, tasks, cidfile, context="", cpu_only=True):
    return _cpu(_base(name, cidfile, context) + _caches() + [
        "-v", _host_path(receipt_file) + ":/mnt/receipt/receipt.json:ro",
        "-v", _host_path(tasks) + ":/mnt/tasks",
        IMAGE_REF, "verify",
        "--receipt-path", "/mnt/receipt/receipt.json",
        "--tasks-root", "/mnt/tasks",
    ], cpu_only)
def infer_argv(name, tasks, model, prompt, max_new_tokens, cidfile, context="", cpu_only=True):
    model = _safe_text(model, "model")
    prompt = _safe_text(prompt, "prompt")
    if type(max_new_tokens) is not int:
        raise DockerError("invalid_argument", "max_new_tokens must be an integer.")
    return _cpu(_base(name, cidfile, context) + _caches() + [
        "-v", _host_path(tasks) + ":/mnt/tasks",
        IMAGE_REF, "run-all",
        "--model-name", model, "--prompt-text", prompt,
        "--max-new-tokens", str(max_new_tokens),
        "--tasks-root", "/mnt/tasks",
    ], cpu_only)
def _remove(name, env, context=""):
    if not name.startswith("gensyn-ree-"): return False
    head = _head(context)
    try:
        run_child(head + ["rm", "-f", name], b"", env, 15)
        listed = run_child(
            head + ["ps", "-a", "--filter", "name=" + name, "--format", "{{.Names}}"], b"", env, 15,
        )
    except ChildError: return True
    return name in listed.stdout.decode("utf-8", "replace").split()
def leftover_rows(context=""):
    try: listed = run_child(_head(context) + [
            "ps", "-a", "--filter", "name=gensyn-ree-", "--format", "{{.Names}}\t{{.State}}",
        ], b"", child_env(), 15)
    except ChildError: return []
    if listed.returncode != 0: return []
    rows = []
    for line in listed.stdout.decode("utf-8", "replace").splitlines():
        name, _, state = line.strip().partition("\t")
        if name.startswith("gensyn-ree-"): rows.append({"name": name, "state": state or "unknown"})
    return rows
def _ran(argv):
    try: return run_child(argv, b"", child_env(), 15)
    except ChildError: return None
def docker_text(argv):
    result = _ran(argv)
    if result is None or result.returncode != 0: return None
    return result.stdout.decode("utf-8", "replace").strip()
def classify_unstarted(context=""):
    head = _head(context)
    version = _ran(head + ["version", "--format", "{{.Server.Version}}"])
    if version is None or version.returncode != 0: return "docker_unavailable"
    image = _ran(head + ["image", "inspect", IMAGE_REF, "--format", "{{.Id}} {{json .RepoDigests}}"])
    if image is None or image.returncode != 0 or IMAGE_DIGEST.encode() not in image.stdout:
        return "image_missing"
    return "container_not_started"
def start_message(kind):
    if kind == "docker_unavailable": return "Docker daemon is not reachable. No container was started."
    if kind == "image_missing": return image_absent_message()
    return "Docker did not start a container."
def cid_started(path):
    try: return bool(Path(path).read_text().strip())
    except OSError: return False
def _context_of(argv):
    if len(argv) >= 3 and argv[0] == "docker" and argv[1] == "--context": return argv[2]
    return ""
def run_named(argv, deadline, name=None):
    env, label, context = child_env(), name or "", _context_of(argv)
    where = context or "the current Docker daemon"
    try: return run_child(argv, b"", env, deadline)
    except ChildError as exc:
        left = _remove(label, env, context) if label else False
        note = (" Container " + label + " on " + where + " is still running.") if label and left else ""
        if label and not left: note = " Removed container " + label + " on " + where + "."
        on = where if label else ""
        raise DockerError(exc.kind, str(exc) + note, on, label, not left) from None
    except KeyboardInterrupt:
        if label: _remove(label, env, context)
        raise
def _workdir():
    return _mkdir(_cache_root() / "hermes-ree" / "work")
def make_tasks():
    path = Path(tempfile.mkdtemp(prefix="gensyn-ree-tasks-", dir=_workdir()))
    path.chmod(0o700)
    return path
def stage_receipt(payload):
    folder = Path(tempfile.mkdtemp(prefix="gensyn-ree-receipt-", dir=_workdir()))
    path = folder / "receipt.json"
    path.write_bytes(payload)
    path.chmod(0o600)
    folder.chmod(0o700)
    return path
def remove_tree(path):
    if path is not None: shutil.rmtree(path, ignore_errors=True)
