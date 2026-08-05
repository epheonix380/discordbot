"""Database access helpers that survive a Postgres restart.

Why this module exists
----------------------
The bot is a single long-running process. It never goes through Django's
HTTP request cycle, so Django's automatic "close obsolete/broken database
connections" hooks (which normally fire on request_started / request_finished)
NEVER run here.

Consequence, seen in production 2026-07-23: the host Postgres restarted, every
cached Django connection died, and because nothing ever reset them, EVERY query
raised `psycopg2.InterfaceError: connection already closed` -- forever. The
Discord gateway stayed connected (its heartbeat kept refreshing), so the
container looked "healthy" and the watchdog never restarted it. The bot was up
but functionally dead for ~2 days.

The fix
-------
Wrap every threaded DB helper so `close_old_connections()` runs immediately
before (and after) the ORM work, in the same worker thread that runs the query.
`close_old_connections()` drops any connection that is dead or past its max age,
forcing Django to reconnect on the next query. With `CONN_MAX_AGE = 0`
(see backend/settings.py) every connection is considered obsolete, so each call
gets a fresh, verified connection. A future Postgres restart now self-heals on
the next query instead of wedging the bot.

Usage
-----
This is a drop-in replacement for `asgiref.sync.sync_to_async`. Anywhere that
did:

    from asgiref.sync import sync_to_async

for database work, import from here instead:

    from helpers.db import sync_to_async

Both the bare `@sync_to_async` and the parameterised
`@sync_to_async(thread_sensitive=...)` forms work, as does the inline
`sync_to_async(func)(...)` call form.
"""

from functools import wraps

from asgiref.sync import sync_to_async as _asgiref_sync_to_async
from django.db import close_old_connections


def _guard(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        # Runs inside the sync executor thread, the same thread the ORM query
        # runs in, so it operates on that thread's connection.
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return guarded


def sync_to_async(func=None, **kwargs):
    """Resilient stand-in for asgiref.sync.sync_to_async for DB work."""

    def decorator(fn):
        return _asgiref_sync_to_async(_guard(fn), **kwargs)

    if func is not None:
        # Used as `@sync_to_async` or `sync_to_async(fn)`.
        return decorator(func)
    # Used as `@sync_to_async(thread_sensitive=...)`.
    return decorator
