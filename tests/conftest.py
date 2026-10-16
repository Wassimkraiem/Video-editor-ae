"""Isolate tests from a developer's local `.env`.

Environment variables take precedence over the `.env` file in
pydantic-settings, so pinning them here keeps tests on the in-memory
repository and temporary folders even when `.env` points at Postgres.
"""

import os
import tempfile

_root = tempfile.mkdtemp(prefix="video-editor-tests-")
os.environ["DATABASE_URL"] = "memory://"
os.environ["STORAGE_ROOT"] = os.path.join(_root, "storage")
os.environ["PROJECTS_ROOT"] = os.path.join(_root, "projects")
os.environ["LOCAL_WORKER_ENABLED"] = "false"
os.environ["STYLE_EXTRACTION_ENABLED"] = "true"
os.environ.pop("ANTHROPIC_API_KEY", None)
