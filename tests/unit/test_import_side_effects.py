"""Importing app.* must perform NO disk I/O.

Before the lazy-agent refactor, `app/__init__.py` did `from .agent import app`,
which built the pipeline + called build_storage().init_schema() — creating and
migrating a SQLite file merely by importing any app.* submodule. We run the
import in a FRESH interpreter (subprocess) so the assertion can't be masked by
modules already imported in this test session.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_importing_app_creates_no_db(tmp_path):
    db = tmp_path / "should_not_exist.db"
    repo = Path(__file__).resolve().parents[2]
    code = (
        "import app.core.domain\n"
        "import app.runner\n"
        "import app.agent\n"  # importing must NOT build the App (only attr access does)
        "print('imported-ok')\n"
    )
    env = {
        **os.environ,
        "SQLITE_PATH": str(db),
        "SESSION_DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "imported-ok" in result.stdout
    assert not db.exists(), "importing app.* created a SQLite DB (import-time side effect)"


def test_agent_app_is_buildable_on_access(tmp_path):
    """ADK accesses app.agent.app / .root_agent via hasattr; that must build it."""
    repo = Path(__file__).resolve().parents[2]
    code = (
        "import app.agent\n"
        "assert app.agent.root_agent is not None\n"
        "assert app.agent.app.name == 'app'\n"
        "print('built-ok')\n"
    )
    env = {
        **os.environ,
        "SQLITE_PATH": str(tmp_path / "catchup.db"),
        "SESSION_DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "built-ok" in result.stdout
