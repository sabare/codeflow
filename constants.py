from __future__ import annotations

import builtins
import sys


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
}


BUILTIN_NAMES = {name for name in dir(builtins) if not name.startswith("_")}
STDLIB_MODULES = set(getattr(sys, "stdlib_module_names", set()))
