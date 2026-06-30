"""Shared test harness for the context-engineering-blueprint plugin.

FROZEN public API (BRIEF2 "Test architecture"). All test authors import this
module; do NOT redefine these names elsewhere.

Cleanup convention
------------------
Helpers that create a temporary tree (`make_repo`, `mkdtemp`) return a path and
do NOT register cleanup themselves. The CALLER is responsible for removal, e.g.:

    root = make_repo({"docs/_system/glossary.md": "..."})
    self.addCleanup(shutil.rmtree, root, ignore_errors=True)

This keeps the harness free of any global/auto-cleanup state and makes the
ownership of each temp tree explicit in the test that created it.

Stdlib only. No pip, no network.
"""

import importlib
import importlib.util
import io
import json
import os
import sys
import tempfile

# --- Frozen path constants -------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))            # plugin/tests
PLUGIN_ROOT = os.path.dirname(HERE)                          # plugin/
SCRIPTS = os.path.join(PLUGIN_ROOT, "scripts")              # plugin/scripts
TEMPLATES = os.path.join(PLUGIN_ROOT, "templates")         # plugin/templates

# The design dir (slice files + MASTER) — optional, only present in the dev
# environment. Used for any data-parity checks. None when absent.
_DESIGN_CANDIDATE = os.path.join(PLUGIN_ROOT, "..", "design")
DESIGN_DIR = os.path.abspath(_DESIGN_CANDIDATE) if os.path.isdir(_DESIGN_CANDIDATE) else None

# Make the underscore cores and hyphenated entry scripts importable.
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


# --- Module loading --------------------------------------------------------

def load_core(modname):
    """Import an underscore core module (e.g. load_core("_registry")).

    `modname` is a valid Python module name living in plugin/scripts. The
    module is (re)loaded fresh so tests see the current source on disk.
    """
    if modname.endswith(".py"):
        modname = modname[:-3]
    if modname in sys.modules:
        return importlib.reload(sys.modules[modname])
    return importlib.import_module(modname)


def load_script(name):
    """Import a hyphenated entry script (e.g. "docs-linter" or "docs-linter.py").

    Hyphens are not valid in Python module names, so the script is loaded via
    importlib from its file path under a synthetic module name:
        module name = '_ep_' + basename.replace('-', '_')
    The module is reloaded from disk on every call.
    """
    if not name.endswith(".py"):
        name = name + ".py"
    path = os.path.join(SCRIPTS, name)
    basename = os.path.basename(name)[:-3]                  # strip .py
    modname = "_ep_" + basename.replace("-", "_")
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load entry script: %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


# --- Hook invocation -------------------------------------------------------

def invoke(name, argv=None, stdin_obj=None):
    """Run an entry script's main() with a synthetic argv / stdin.

    - argv: extra args after the program name (sys.argv = [name] + argv).
    - stdin_obj: a dict (JSON-encoded onto stdin), a str (used verbatim), or
      None (empty stdin).
    Captures stdout, calls module.main(), restores sys.argv/sys.stdin/sys.stdout.
    Returns (stdout_str, exit_code). A SystemExit raised by main() is caught and
    its code (default 0) becomes the exit_code.
    """
    module = load_script(name)
    argv = list(argv) if argv else []

    if isinstance(stdin_obj, dict):
        stdin_text = json.dumps(stdin_obj)
    elif stdin_obj is None:
        stdin_text = ""
    else:
        stdin_text = stdin_obj

    old_argv = sys.argv
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    captured = io.StringIO()
    exit_code = 0
    try:
        sys.argv = [name] + argv
        sys.stdin = io.StringIO(stdin_text)
        sys.stdout = captured
        result = module.main()
        if isinstance(result, int):
            exit_code = result
    except SystemExit as exc:
        code = exc.code
        if code is None:
            exit_code = 0
        elif isinstance(code, int):
            exit_code = code
        else:
            exit_code = 1
    finally:
        sys.argv = old_argv
        sys.stdin = old_stdin
        sys.stdout = old_stdout
    return captured.getvalue(), exit_code


def hook_stdin(event, tool_name=None, tool_input=None, **extra):
    """Build a hook stdin envelope (MASTER §3.1).

    Always sets the common fields (session_id, transcript_path, cwd,
    hook_event_name). Adds tool_name/tool_input when given. Any extra keyword
    (e.g. tool_response, source, reason) is merged in verbatim.
    """
    envelope = {
        "session_id": "test-session",
        "transcript_path": "/tmp/test-transcript.jsonl",
        "cwd": os.getcwd(),
        "hook_event_name": event,
    }
    if tool_name is not None:
        envelope["tool_name"] = tool_name
    if tool_input is not None:
        envelope["tool_input"] = tool_input
    envelope.update(extra)
    return envelope


# --- Temp repos / docs -----------------------------------------------------

def mkdtemp():
    """Create and return a fresh temporary directory path. Caller cleans up."""
    return tempfile.mkdtemp(prefix="ceb-test-")


def make_repo(files):
    """Create a temp dir and write `files` (relpath -> str content) into it.

    Parent directories are created as needed. Returns the repo root path. The
    caller is responsible for cleanup (see module docstring).
    """
    root = mkdtemp()
    for relpath, content in (files or {}).items():
        abspath = os.path.join(root, relpath)
        os.makedirs(os.path.dirname(abspath) or root, exist_ok=True)
        with open(abspath, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
    return root


# Stable key order for rendered frontmatter (matches §3.4 schema ordering, then
# any author-supplied extras in their given order).
_FM_KEY_ORDER = (
    "id", "title", "type", "domain", "status", "owner",
    "created", "updated", "review_by",
    "depends_on", "impacts", "canonical_for", "llm_context",
    "superseded_by", "sources",
)


def _render_fm_value(value):
    """Render a single frontmatter value to its YAML-ish scalar/flow form."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def fm_block(fm):
    """Render a dict as a `--- ... ---` frontmatter block.

    Keys are emitted in the stable §3.4 order
    (id, title, type, domain, status, owner, created, updated, review_by,
     depends_on, impacts, canonical_for, llm_context, superseded_by, sources)
    followed by any extra keys in their dict insertion order. Lists render as
    inline flow (`[a, b]`); None renders as a blank value.
    """
    fm = fm or {}
    lines = ["---"]
    seen = set()
    for key in _FM_KEY_ORDER:
        if key in fm:
            seen.add(key)
            rendered = _render_fm_value(fm[key])
            lines.append("%s:%s" % (key, (" " + rendered) if rendered != "" else ""))
    for key, value in fm.items():
        if key in seen:
            continue
        rendered = _render_fm_value(value)
        lines.append("%s:%s" % (key, (" " + rendered) if rendered != "" else ""))
    lines.append("---")
    return "\n".join(lines) + "\n"


def write_doc(root, relpath, fm, body=""):
    """Render frontmatter+body, write under `root/relpath`, return abspath."""
    abspath = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(abspath) or root, exist_ok=True)
    text = fm_block(fm)
    if body:
        text = text + body
    with open(abspath, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return abspath


def read(path):
    """Read a UTF-8 text file and return its contents."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()
