import threading

from app.core.config import Settings
from app.core.env_store import _format_value, upsert_env


def test_upsert_creates_file_with_value(tmp_path):
    p = tmp_path / ".env"
    upsert_env(p, {"GOOGLE_API_KEY": "abc123"})
    assert p.read_text(encoding="utf-8") == "GOOGLE_API_KEY=abc123\n"


def test_upsert_replaces_in_place_preserving_other_lines(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# header\nKEEP=stay\nGOOGLE_API_KEY=old\n", encoding="utf-8")
    upsert_env(p, {"GOOGLE_API_KEY": "new"})
    assert p.read_text(encoding="utf-8") == "# header\nKEEP=stay\nGOOGLE_API_KEY=new\n"


def test_upsert_appends_missing_key(tmp_path):
    p = tmp_path / ".env"
    p.write_text("EXISTING=1\n", encoding="utf-8")
    upsert_env(p, {"APP_PORT": "9000"})
    assert p.read_text(encoding="utf-8") == "EXISTING=1\nAPP_PORT=9000\n"


def test_format_value_quotes_only_when_needed():
    assert _format_value("simpleKey-123_x") == "simpleKey-123_x"
    assert _format_value("has space") == '"has space"'
    assert _format_value("a#b") == '"a#b"'
    assert _format_value("") == '""'
    assert _format_value('a"b') == '"a\\"b"'
    assert _format_value("a\\b") == '"a\\\\b"'


def test_value_with_hash_and_spaces_roundtrips_through_settings(tmp_path, monkeypatch):
    # Strongest check: a value that would otherwise be truncated at '#' or split
    # on whitespace must survive the EXACT parser pydantic-settings uses.
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    p = tmp_path / ".env"
    upsert_env(p, {"GOOGLE_API_KEY": "hello world#x"})
    assert Settings(_env_file=str(p)).google_api_key == "hello world#x"


def test_upsert_dedups_existing_duplicate_keys(tmp_path, monkeypatch):
    # Two pre-existing lines for the same key: after update there must be exactly one,
    # carrying the new value (dotenv is last-wins; a stale 2nd line would shadow us).
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    p = tmp_path / ".env"
    p.write_text("GOOGLE_API_KEY=old1\nKEEP=x\nGOOGLE_API_KEY=old2\n", encoding="utf-8")
    upsert_env(p, {"GOOGLE_API_KEY": "new"})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert sum(1 for ln in lines if ln.startswith("GOOGLE_API_KEY=")) == 1
    assert Settings(_env_file=str(p)).google_api_key == "new"


def test_upsert_sets_0600_permissions(tmp_path):
    p = tmp_path / ".env"
    upsert_env(p, {"A": "1"})
    assert (p.stat().st_mode & 0o777) == 0o600


def test_upsert_leaves_no_temp_files(tmp_path):
    p = tmp_path / ".env"
    upsert_env(p, {"A": "1"})
    upsert_env(p, {"B": "2"})
    assert [x.name for x in tmp_path.iterdir()] == [".env"]


def test_concurrent_upserts_do_not_lose_keys(tmp_path):
    p = tmp_path / ".env"
    upsert_env(p, {"BASE": "0"})
    keys = [f"K{i}" for i in range(24)]
    threads = [threading.Thread(target=upsert_env, args=(p, {k: k.lower()})) for k in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines = p.read_text(encoding="utf-8").splitlines()
    present = {ln.split("=", 1)[0] for ln in lines if "=" in ln}
    assert present == {"BASE", *keys}
    # no key appears twice (no corruption / duplicate append under the lock)
    assert len(lines) == len(present)
