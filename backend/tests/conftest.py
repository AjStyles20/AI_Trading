"""Point the whole test session at a temporary data folder.

This runs before any test module imports the database code, which reads
ASTRAL_DATA_DIR once at import. Tests can then never touch a developer's real
database, even ones that write through code that logs to it.
"""
import os
import tempfile

os.environ["ASTRAL_DATA_DIR"] = tempfile.mkdtemp(prefix="astral-tests-")
