"""One gate for both catalog drafts. Checks return typed pairs, not prose."""
from __future__ import annotations

from pathlib import Path


class _Yaml:
    """Load PyYAML on first use. Importing this module does not require it."""

    def __getattr__(self, name):
        import yaml
        return getattr(yaml, name)


yaml = _Yaml()

PUBLIC_REPO = "https://github.com/TakeshiTGAL/hermes-gensyn-plugins"
ROWS = (
    ("hermes-gensyn-delphi", "packages/delphi", ">=0.21.4"),
    ("hermes-gensyn-ree", "packages/ree", ">=0.21.6"),
)


def problems(document, row):
    name, subdir, requires = row
    if not isinstance(document, dict):
        return (("document", type(document).__name__),)
    found = []
    checks = (
        ("name", document.get("name"), name),
        ("subdir", document.get("subdir"), subdir),
        ("repo", document.get("repo"), PUBLIC_REPO),
        ("requires_hermes", document.get("requires_hermes"), requires),
    )
    for key, got, want in checks:
        if got != want or (key == "requires_hermes" and not isinstance(got, str)):
            found.append((key, got))
    return tuple(found)


def load_rows(repo):
    repo = Path(repo)
    loaded = []
    for row in ROWS:
        text = (repo / "catalog" / f"{row[0]}.yaml").read_text()
        document = yaml.safe_load(text)
        plugin = yaml.safe_load((repo / row[1] / "plugin.yaml").read_text())
        found = problems(document, row)
        plugin_requires = plugin.get("requires_hermes") if isinstance(plugin, dict) else None
        if plugin_requires != row[2] or not isinstance(plugin_requires, str):
            found = found + (("plugin.requires_hermes", plugin_requires),)
        loaded.append((row, text, document, found))
    return tuple(loaded)


def unquoted_requires_fails(text):
    broken = text.replace('requires_hermes: ">=', "requires_hermes: >=", 1)
    if broken == text:
        return False
    try:
        yaml.safe_load(broken)
    except yaml.YAMLError:
        return True
    return False


def loader_names(directory):
    try:
        from hermes_cli.plugin_catalog import load_catalog
    except (ImportError, TypeError):
        return None
    return tuple(entry.name for entry in load_catalog(Path(directory)))


def check_drafts(repo, tmp_path=None):
    rows = load_rows(repo)
    bad = tuple((row[0], found) for row, _text, _document, found in rows if found)
    if bad:
        raise AssertionError(bad)
    for row, text, _document, _found in rows:
        if not unquoted_requires_fails(text):
            raise AssertionError(("unquoted_requires", row[0]))
    names = loader_names(Path(repo) / "catalog")
    if names is None or tmp_path is None:
        return names
    if names != HTTPS_NAMES:
        raise AssertionError(("https_repo", names))
    return names


HTTPS_NAMES = ("hermes-gensyn-delphi", "hermes-gensyn-ree")
LOADER_RESULTS = (
    ("loader", "absent"),
    ("loader", "https", HTTPS_NAMES),
)


def loader_verdict(repo, tmp_path):
    """Typed result of check_drafts. Does not replace that gate."""
    names = check_drafts(repo, tmp_path)
    if names is None:
        return ("loader", "absent")
    if names == HTTPS_NAMES:
        return ("loader", "https", names)
    return ("loader", "unexpected", names)


def _field(text, key):
    prefix = key + ": "
    for line in text.splitlines():
        if line.startswith(prefix):
            raw = line[len(prefix):].strip()
            if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
                return raw[1:-1]
            return raw
    return None


def requires_form(text):
    hits = [line.strip() for line in text.splitlines() if line.strip().startswith("requires_hermes:")]
    if len(hits) != 1:
        return ("requires", "other")
    line = hits[0]
    if line.startswith("requires_hermes: \">=") and line.endswith('"'):
        return ("requires", "quoted")
    if line.startswith("requires_hermes: >="):
        return ("requires", "unquoted")
    return ("requires", "other")


REQUIRES_SAMPLES = (
    ('requires_hermes: ">=0.21.4"', ("requires", "quoted")),
    ('requires_hermes: ">=0.21.6"', ("requires", "quoted")),
    ("requires_hermes: >=0.21.4", ("requires", "unquoted")),
    ("requires_hermes: >=0.21.6", ("requires", "unquoted")),
    ("requires_hermes: 0.21.4", ("requires", "other")),
)


def _draft_problems(repo):
    repo = Path(repo)
    found = []
    for name, subdir, requires in ROWS:
        catalog = (repo / "catalog" / (name + ".yaml")).read_text()
        plugin = (repo / subdir / "plugin.yaml").read_text()
        pairs = (
            ("name", _field(catalog, "name"), name),
            ("subdir", _field(catalog, "subdir"), subdir),
            ("repo", _field(catalog, "repo"), PUBLIC_REPO),
            ("requires_hermes", _field(catalog, "requires_hermes"), requires),
            ("plugin.requires_hermes", _field(plugin, "requires_hermes"), requires),
        )
        for key, got, want in pairs:
            if got != want:
                found.append((name, key, got, want))
        for label, body in (("catalog", catalog), ("plugin", plugin)):
            form = requires_form(body)
            if form != ("requires", "quoted"):
                found.append((name, label, form))
    return tuple(found)


DRAFT_RESULTS = (
    ("draft", "quoted"),
    ("draft", "full", ("loader", "absent")),
    ("draft", "full", ("loader", "https", HTTPS_NAMES)),
)


def draft_verdict(repo, tmp_path):
    """Stdlib read of both drafts. Calls loader_verdict only when PyYAML imports."""
    bad = _draft_problems(repo)
    if bad:
        return ("draft", "bad", bad)
    try:
        yaml.safe_load("name: ok\n")
    except ModuleNotFoundError:
        return ("draft", "quoted")
    verdict = loader_verdict(repo, tmp_path)
    if verdict not in LOADER_RESULTS:
        return ("draft", "unexpected", verdict)
    return ("draft", "full", verdict)


NPM_CI_PATHS = (
    "README.md",
    "CONTRIBUTING.md",
    "packages/delphi/README.md",
    "packages/delphi/doctor.py",
    ".github/workflows/tests.yml",
    ".github/workflows/smoke-test.yml",
)
NPM_CI_RESULTS = (("npm_ci", "directory"),)


def npm_ci_forms(text):
    forms = []
    for line in text.splitlines():
        if "npm ci" not in line:
            continue
        if "--prefix" in line:
            forms.append(("npm_ci", "prefix"))
        elif "npm ci --ignore-scripts" not in line:
            forms.append(("npm_ci", "other"))
        else:
            forms.append(("npm_ci", "directory"))
    return tuple(forms)


NPM_CI_SAMPLES = (
    ("cd packages/delphi\nnpm ci --ignore-scripts\n", ("npm_ci", "directory")),
    (
        "( cd \"$HERMES_HOME/plugins/hermes-gensyn-delphi\""
        " && npm ci --ignore-scripts )\n",
        ("npm_ci", "directory"),
    ),
    ("working-directory: packages/delphi\nrun: npm ci --ignore-scripts\n", ("npm_ci", "directory")),
    ("npm ci --ignore-scripts\n", ("npm_ci", "directory")),
    ("npm ci --ignore-scripts --prefix packages/delphi\n", ("npm_ci", "prefix")),
    ("cd packages/delphi\nnpm ci --ignore-scripts --prefix .\n", ("npm_ci", "prefix")),
    ("Run npm ci --ignore-scripts in packages/delphi.\n", ("npm_ci", "directory")),
    ("npm ci\n", ("npm_ci", "other")),
)


def _prefix_hits(repo):
    skip = {".git", "node_modules", "__pycache__", ".pytest_cache"}
    hits = []
    for path in Path(repo).rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".yml", ".yaml", ".py", ".mjs"}:
            continue
        if any(part in skip for part in path.parts) or path.name == "gate.py":
            continue
        for index, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if "npm ci" in line and "--prefix" in line:
                hits.append((str(path.relative_to(repo)), index, ("npm_ci", "prefix")))
    return tuple(hits)


def npm_ci_verdict(repo):
    """Every npm ci line in the table is the directory form, not --prefix."""
    repo = Path(repo)
    bad = list(_prefix_hits(repo))
    seen = 0
    for rel in NPM_CI_PATHS:
        forms = npm_ci_forms((repo / rel).read_text())
        seen += len(forms)
        bad.extend((rel, form) for form in forms if form not in NPM_CI_RESULTS)
    if bad:
        return ("npm_ci", "bad", tuple(bad))
    if seen == 0:
        return ("npm_ci", "absent")
    return ("npm_ci", "directory")
