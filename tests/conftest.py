"""Keep the test suite on the in-memory ADK session service by default so tests
stay fast and write no session DB. Tests that exercise the persistent path pass
session_backend="database" explicitly (init kwargs beat this env var)."""
import os

os.environ.setdefault("SESSION_BACKEND", "memory")
