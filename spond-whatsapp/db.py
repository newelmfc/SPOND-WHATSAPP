"""Simple SQLite helpers for mapping WhatsApp numbers to Spond person IDs.

The database stores a single table ``person_map`` that maps a player's
WhatsApp phone number (in E.164 format) to their Spond ``person_id``.  This
allows the webhook to quickly look up the appropriate Spond identifier when
handling a button reply.

Functions in this module are intentionally small and synchronous; writes
are wrapped in a context to commit automatically, and reads return
``None`` when the mapping isn't found.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator, Optional

# Location of the SQLite database; defaults to ``app.db`` in the current
# working directory. You can override this via the ``DB_PATH`` environment
# variable when deploying.
DB_PATH = os.getenv("DB_PATH", "app.db")


@contextmanager
def _connect() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a connection with threadsafe check disabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialise the ``person_map`` table if it doesn't already exist.

    This function can be called repeatedly; it is safe to run in
    environments where the table may already exist.
    """
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS person_map (
                phone_e164 TEXT PRIMARY KEY,
                person_id TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_person_map_person_id
            ON person_map (person_id)
            """
        )
        conn.commit()


def upsert_person(phone_e164: str, person_id: str) -> None:
    """Insert or update the mapping from a WhatsApp phone number to a person ID.

    Parameters
    ----------
    phone_e164: str
        The WhatsApp phone number in E.164 format (e.g. ``+447700900000``).
    person_id: str
        The unique identifier for the member in Spond. This value is
        returned by the Spond API when listing group members or
        event invitees.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO person_map (phone_e164, person_id)
            VALUES (?, ?)
            ON CONFLICT(phone_e164) DO UPDATE
                SET person_id = excluded.person_id
            """,
            (phone_e164, person_id),
        )
        conn.commit()


def get_person_id(phone_e164: str) -> Optional[str]:
    """Retrieve the Spond ``person_id`` associated with a given phone number.

    Parameters
    ----------
    phone_e164: str
        The WhatsApp phone number in E.164 format (e.g. ``+447700900000``).

    Returns
    -------
    Optional[str]
        The associated ``person_id`` if found, otherwise ``None``.
    """
    with _connect() as conn:
        cur = conn.execute(
            "SELECT person_id FROM person_map WHERE phone_e164 = ? LIMIT 1",
            (phone_e164,),
        )
        row = cur.fetchone()
        return row[0] if row else None
