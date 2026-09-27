"""
Root conftest for backend tests.

Sets the DEBUG environment variable to a valid boolean string before any
test module is imported.  This is needed because the OS shell may set
DEBUG=release (a non-boolean value that pydantic-settings rejects for a
`bool` field).  Setting it here, before `config.py` is imported, prevents
the ValidationError that would otherwise block test collection.
"""

import os

# Must happen before any import of backend.app.core.config (which instantiates
# Settings() at module level).  Conftest files are loaded by pytest before
# test modules are collected, so this assignment fires at the right time.
os.environ.setdefault("DEBUG", "False")
# If DEBUG is already set to a non-boolean value, override it explicitly.
_debug_val = os.environ.get("DEBUG", "False")
if _debug_val.lower() not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
    os.environ["DEBUG"] = "False"
