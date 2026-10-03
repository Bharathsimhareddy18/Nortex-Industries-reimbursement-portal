"""The shared resources: one set, opened by the app's lifespan, handed to everything that needs them, closed at shutdown."""
import asyncio

import pytest
from fastapi.testclient import TestClient

import src.database.db as dbmod
from main import app
from src.resources import Resources


def test_resources_are_shared_and_closed_at_shutdown(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_FILE", tmp_path / "test.db")
    with pytest.raises(RuntimeError):
        Resources.get()  # nothing is open before the app starts
    with TestClient(app):
        first = Resources.get()
        assert Resources.get() is first and not first.http.is_closed  # one instance, one HTTP client
        with pytest.raises(RuntimeError):
            asyncio.run(Resources().__aenter__())  # a second set cannot be opened
    assert first.http.is_closed  # closed when the app stopped
    with pytest.raises(RuntimeError):
        Resources.get()
