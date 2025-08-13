"""Helper functions for interacting with the WhatsApp Cloud API.

This module provides a small wrapper around the HTTP endpoints needed to
send messages and interactive reply buttons via WhatsApp Business API.
By centralising the HTTP logic here, the rest of your application code
remains clean and focused on business rules.

Note: The functions in this module use ``httpx`` for async HTTP requests.
If you call these from synchronous code, remember to run them inside an
``asyncio`` event loop. In the FastAPI environment used by ``app.py``
this happens implicitly.
"""

from __future__ import annotations

import os
from typing import List, Optional

import httpx

WABA_TOKEN = os.getenv("WABA_TOKEN")
WABA_PHONE_ID = os.getenv("WABA_PHONE_ID")

GRAPH_BASE_URL = os.getenv("GRAPH_BASE", "https://graph.facebook.com/v20.0")


def _auth_headers() -> dict:
    if not WABA_TOKEN:
        raise ValueError("WABA_TOKEN must be set in environment variables")
    return {"Authorization": f"Bearer {WABA_TOKEN}"}


async def send_template(
    to_e164: str,
    template_name: str,
    lang: str = "en_GB",
    components: Optional[list] = None,
) -> dict:
    """Send a pre-approved WhatsApp template message.

    Use this method to initiate a conversation outside the 24h customer
    care window. Templates must be approved by Meta before they can be
    sent; you'll need to configure them in your WhatsApp Business
    dashboard.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
        },
    }
    if components:
        payload["template"]["components"] = components
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{GRAPH_BASE_URL}/{WABA_PHONE_ID}/messages",
            headers=_auth_headers(),
            json=payload,
        )
        response.raise_for_status()
        return response.json()


async def send_availability_buttons(
    to_e164: str, event_id: str, title: str
) -> dict:
    """Send a message with three reply buttons for availability.

    The ``event_id`` is embedded in each button's ID string so that
    your webhook knows which event the response relates to. The ID
    format is ``EVT:<event_id>:<CHOICE>``. WhatsApp allows up to
    256 characters for the reply ID, which should be sufficient for
    the event ID returned by Spond.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"{title}\nAre you available?"},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": f"EVT:{event_id}:YES", "title": "Yes"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": f"EVT:{event_id}:MAYBE", "title": "Maybe"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": f"EVT:{event_id}:NO", "title": "No"},
                    },
                ]
            },
        },
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{GRAPH_BASE_URL}/{WABA_PHONE_ID}/messages",
            headers=_auth_headers(),
            json=payload,
        )
        response.raise_for_status()
        return response.json()


async def send_text(to_e164: str, body: str) -> dict:
    """Send a plain text message to a WhatsApp user.

    This is useful for confirming actions (e.g. "Got it – marked you
    attending") or notifying the user when there's an error mapping
    their number.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164,
        "type": "text",
        "text": {"body": body},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{GRAPH_BASE_URL}/{WABA_PHONE_ID}/messages",
            headers=_auth_headers(),
            json=payload,
        )
        response.raise_for_status()
        return response.json()
