"""Wrapper around the unofficial ``spond`` Python package.

This module provides an async-friendly helper class ``SpondClient`` that
abstracts away the raw calls to the unofficial Spond API library. The goal
is to encapsulate the functionality your bot needs: listing upcoming events,
fetching information about members, determining which invitees still need to
respond, and updating a member's response to an event.

The ``spond`` library performs network requests under the hood; here we
wrap those calls so they integrate neatly into a FastAPI application.

**Important**: Because this library is unofficial, it may break without
warning if Spond changes their API or login mechanisms. Always monitor
error logs and consider switching to an officially supported endpoint
should one become available.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from spond import spond as spond_async


# Read credentials from environment variables. When used in a deployment
# environment (e.g. Render), these values should be set as secrets.
SPOND_USER = os.getenv("SPOND_USER")
SPOND_PASS = os.getenv("SPOND_PASS")


class SpondClient:
    """Async context manager for communicating with Spond.

    To use, instantiate ``SpondClient`` and call the methods on it.
    Remember to close the client afterwards to free underlying network
    resources. In an async environment such as FastAPI, you should use
    ``async with SpondClient() as sc: ...`` to ensure proper closure.
    """

    def __init__(self) -> None:
        if not SPOND_USER or not SPOND_PASS:
            raise ValueError(
                "SPOND_USER and SPOND_PASS must be set in environment variables"
            )
        # The spond library uses async HTTP; no session is created until needed.
        self._client = spond_async.Spond(username=SPOND_USER, password=SPOND_PASS)

    async def __aenter__(self) -> "SpondClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the internal HTTP session if it's open."""
        # The spond module lazily creates the clientsession on first call.
        try:
            await self._client.clientsession.close()
        except Exception:
            pass

    async def upcoming_events(self, days_ahead: int = 14) -> List[dict]:
        """Return events starting within the next ``days_ahead`` days.

        Parameters
        ----------
        days_ahead : int
            Number of days ahead of now to include when fetching events.

        Returns
        -------
        List[dict]
            A list of event dictionaries as returned by the unofficial
            ``spond`` library. Each event includes keys such as ``id``,
            ``heading``, ``startDate`` and a nested ``responses`` dict
            containing buckets of person IDs by RSVP state.
        """
        now = datetime.now(timezone.utc)
        return await self._client.get_events(
            min_start=now, max_start=now + timedelta(days=days_ahead)
        )

    async def get_person(self, person_id: str) -> dict:
        """Fetch details of a single member by their ``person_id``.

        Returns a dictionary with keys including ``firstName``, ``lastName``,
        ``phone`` or ``mobile``, and other profile details.
        """
        return await self._client.get_person(person_id)

    async def people_needing_response(self, event: dict) -> List[str]:
        """Return a list of person IDs who have yet to confirm attendance.

        Spond categorises responses into buckets such as
        ``unansweredIds`` and ``unconfirmedIds``. We merge both sets and
        return the unique identifiers.
        """
        responses = event.get("responses") or {}
        unanswered = set(responses.get("unansweredIds", []))
        unconfirmed = set(responses.get("unconfirmedIds", []))
        return list(unanswered | unconfirmed)

    async def set_response(self, event_id: str, person_id: str, status: str) -> None:
        """Set a person's RSVP status for an event.

        Parameters
        ----------
        event_id : str
            Unique identifier of the event in Spond.
        person_id : str
            Unique identifier of the member responding to the event.
        status : str
            Must be one of ``attending``, ``maybe``, or ``declined``. Any
            other value will be sent to the underlying API as-is and may
            result in an error.
        """
        await self._client.change_response(
            event_id=event_id, person_id=person_id, response=status
        )
