"""Docker credentials must reach migrations and Uvicorn without URL corruption."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from backend import docker_entrypoint


def test_compose_credentials_and_command(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "compose_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "local:p@ss/with%reserved?#")
    monkeypatch.setenv("POSTGRES_DB", "compose_test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    command = ["python", "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"]
    monkeypatch.setattr(docker_entrypoint.sys, "argv", ["entrypoint", *command])
    executed = []
    monkeypatch.setattr(docker_entrypoint.os, "execvp", lambda *args: executed.append(args))
    docker_entrypoint.main()
    url = make_url(docker_entrypoint.os.environ["DATABASE_URL"])
    assert (url.username, url.password, url.database, url.host, url.port) == (
        "compose_user", "local:p@ss/with%reserved?#", "compose_test", "postgres", 5432,
    )
    assert executed == [("python", command)]


def test_explicit_managed_database_url_is_preserved(monkeypatch):
    database_url = "postgresql+psycopg2://managed:secret@db.example/studentsuccessful"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(docker_entrypoint.sys, "argv", ["entrypoint", "python", "-V"])
    executed = []
    monkeypatch.setattr(docker_entrypoint.os, "execvp", lambda *args: executed.append(args))

    docker_entrypoint.main()

    assert docker_entrypoint.os.environ["DATABASE_URL"] == database_url
    assert executed == [("python", ["python", "-V"])]


def test_alembic_accepts_percent_encoded_credentials():
    # Offline SQL generation traverses env.py/ConfigParser without needing this host.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head", "--sql"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DATABASE_URL": "postgresql+psycopg2://user:p%40ss%25word@postgres/test"},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE users" in result.stdout
