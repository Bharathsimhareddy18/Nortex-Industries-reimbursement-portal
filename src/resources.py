"""The app's shared resources: ONE database engine and ONE HTTP client (for Groq), opened once at startup and closed at shutdown.

    async with Resources() as resources:      # main.py's lifespan does exactly this
        ...                                    # the app runs
    # leaving the block closes the HTTP connections and the database pool

It is a singleton: only one can be open at a time, and anything that needs a resource asks for it with Resources.get(), so
nothing creates its own engine or client. Handlers in this app are plain `def` (they run in a thread pool), so the HTTP client is
the sync httpx.Client, which is safe to share between threads and keeps its connections open between receipts.
"""
import httpx
from sqlalchemy.orm import Session, sessionmaker

from src.database.db import create_tables, make_engine


class Resources:
    _current: "Resources | None" = None  # the one open instance

    async def __aenter__(self) -> "Resources":
        if Resources._current is not None:
            raise RuntimeError("Resources are already open: there is only one set of shared resources")
        self.engine = make_engine()
        create_tables(self.engine)
        self._sessions = sessionmaker(bind=self.engine)
        self.http = httpx.Client(timeout=90)  # used for every Groq call
        Resources._current = self
        return self

    async def __aexit__(self, *_exc) -> None:
        Resources._current = None
        self.http.close()
        self.engine.dispose()

    @classmethod
    def get(cls) -> "Resources":
        """The open resources. Raises if the app (or a script) has not opened them yet."""
        if cls._current is None:
            raise RuntimeError("Resources are not open: use `async with Resources():` (main.py's lifespan does this)")
        return cls._current

    def session(self) -> Session:
        """A new database session on the shared engine. Use it as `with resources.session() as db:`."""
        return self._sessions()
