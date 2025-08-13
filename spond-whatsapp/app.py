"""FastAPI application to bridge WhatsApp and Spond.

The app has two main responsibilities:

* Serve as the WhatsApp webhook, listening for button reply events and
  updating Spond attendance records accordingly.
* Provide an endpoint to synchronise upcoming events from Spond and
  dispatch WhatsApp messages inviting participants to respond.

Usage:

1. Configure your environment variables (``WABA_TOKEN``, ``WABA_PHONE_ID``,
   ``SPOND_USER``, ``SPOND_PASS``, etc.) either via an `.env` file or in
   your deployment settings.
2. Start the FastAPI app with a server such as Uvicorn:

       uvicorn app:app --host 0.0.0.0 --port 8080

3. Expose the `/whatsapp/webhook` endpoint publicly and register it in
   your WhatsApp Business App as the callback URL. Set the same
   ``VERIFY_TOKEN`` in your environment that you specify on the WhatsApp
   dashboard.

4. Trigger the `/sync-and-invite` endpoint (e.g. via cron or manual
   request) to fetch upcoming Spond events and send invitation buttons
   to members who haven't responded.

The logic for mapping phone numbers to person IDs is handled by
``db.py``. When you invite a member, their phone number is stored
alongside their person ID, allowing the webhook to resolve the mapping
when they respond via WhatsApp.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from db import init_db, get_person_id, upsert_person
from spond_adapter import SpondClient
from wa import send_availability_buttons, send_text, send_template

# Load environment variables from a .env file if present. This is useful
# during local development; when deploying to platforms like Render or
# Railway, environment variables are configured through their settings.
load_dotenv()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my-secret")
DEFAULT_DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "14"))

# Create the FastAPI app instance. The title is optional and shows up in
# the OpenAPI documentation at /docs.
app = FastAPI(title="Spond ↔ WhatsApp Bridge")

# Initialize the SQLite database table on startup.
init_db()


def normalise_e164(num: str) -> str:
    """Ensure phone numbers start with a leading '+'.

    WhatsApp sends phone numbers without the plus sign in the webhook
    payload. The Spond API however often stores numbers with the plus
    sign. Normalising to a consistent representation simplifies mapping.
    """
    num = num.strip()
    return num if num.startswith("+") else f"+{num}"


@app.get("/whatsapp/webhook")
async def verify(mode: Optional[str] = None, hub_challenge: Optional[str] = None, hub_verify_token: Optional[str] = None, token: Optional[str] = None, challenge: Optional[str] = None):
    """Verify endpoint for WhatsApp webhook subscription.

    When setting up the webhook in the Meta Developer portal you supply
    a callback URL and a ``VERIFY_TOKEN``. Meta makes a GET request to
    your callback with ``hub.verify_token`` and ``hub.challenge``. If
    the token matches your configured one, you must echo the challenge
    back.
    """
    vt = hub_verify_token or token
    ch = hub_challenge or challenge
    if vt != VERIFY_TOKEN:
        return PlainTextResponse("forbidden", status_code=403)
    return PlainTextResponse(ch or "OK")


@app.post("/whatsapp/webhook")
async def webhook(req: Request):
    """Handle incoming WhatsApp messages (primarily button replies)."""
    data = await req.json()
    # WhatsApp batches notifications; we only process the first entry and
    # message for simplicity. In production you may want to loop.
    try:
        entry = data["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return {"status": "ignored"}

    messages = entry.get("messages", [])
    if not messages:
        return {"status": "ignored"}

    message = messages[0]
    wa_from = normalise_e164(message.get("from", ""))

    interactive = message.get("interactive", {})
    if interactive.get("type") != "button_reply":
        return {"status": "ignored"}

    btn = interactive.get("button_reply", {})
    btn_id = btn.get("id")
    # Expect ID format: EVT:<event_id>:YES|MAYBE|NO
    try:
        _, event_id, choice = btn_id.split(":", 2)
    except Exception:
        await send_text(wa_from, "Sorry, I couldn't process your response. Please ask the coach.")
        return {"status": "bad_button_id"}

    choice_upper = choice.upper()
    status_map = {"YES": "attending", "MAYBE": "maybe", "NO": "declined"}
    status = status_map.get(choice_upper)
    if not status:
        await send_text(wa_from, "Sorry, unknown response choice.")
        return {"status": "invalid_choice"}

    # Look up the Spond person id by phone number.
    person_id = get_person_id(wa_from)
    if not person_id:
        await send_text(wa_from, "Couldn't link your number to any player. Please rejoin via the invite.")
        return {"status": "unmapped_number"}

    # Perform the Spond update within a client context.
    try:
        async with SpondClient() as sc:
            await sc.set_response(event_id=event_id, person_id=person_id, status=status)
    except Exception as exc:
        # Log exception details as needed (not printed to user)
        await send_text(wa_from, "An error occurred updating your status. Try again later.")
        return {"status": "spond_error", "detail": str(exc)}

    # Confirm to the player via WhatsApp.
    await send_text(wa_from, f"Got it — marked you as {status} ✅")
    return {"status": "ok"}


@app.post("/sync-and-invite")
async def sync_and_invite():
    """Synchronise upcoming Spond events and invite members via WhatsApp."""
    invites_sent = 0
    try:
        async with SpondClient() as sc:
            events = await sc.upcoming_events(DEFAULT_DAYS_AHEAD)
            for event in events:
                event_id = event.get("id") or event.get("uid")
                title = event.get("heading", "Upcoming event")
                targets = await sc.people_needing_response(event)
                for person_id in targets:
                    person = await sc.get_person(person_id)
                    # Spond may store phone under "phone" or "mobile"
                    phone = (person.get("phone") or person.get("mobile") or "").strip()
                    if not phone:
                        continue
                    phone_e164 = normalise_e164(phone)
                    # Map phone to person so webhook can resolve it later.
                    upsert_person(phone_e164, person_id)
                    try:
                        await send_availability_buttons(phone_e164, event_id, title)
                        invites_sent += 1
                    except Exception:
                        # Continue to next person if sending fails.
                        pass
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")
    return {"invites_sent": invites_sent}
