Spond ↔ WhatsApp Bridge
========================

This repository contains a small FastAPI application that bridges
**Spond**, an unofficial Python client for Spond events, with the
**WhatsApp Cloud API**. It allows team managers to invite players
via WhatsApp and have their availability recorded back into Spond
automatically.

What it does
------------

* Fetches upcoming Spond events (using the unofficial `spond` package).
* Sends a WhatsApp message with **Yes / Maybe / No** reply buttons to
  members who haven't yet responded to the event. The real Spond event
  ID is embedded in each button's ID.
* Receives button replies on a webhook, matches the sender's phone
  number to their Spond `person_id` via a local SQLite database, and
  updates their response in Spond.

Getting started
---------------

1. **Clone this repo** into your own account and push it to a platform
   that can host a Python web service (e.g. Render, Railway).

2. **Install dependencies**. In your local environment or in a CI build
   script, run:

   ```bash
   pip install -r requirements.txt
   ```

3. **Set environment variables**. Copy `.env.example` to `.env` and
   fill in your own values:

   * `WABA_TOKEN` – a permanent WhatsApp Business API token
   * `WABA_PHONE_ID` – your WhatsApp phone number ID (from the API setup
     page)
   * `VERIFY_TOKEN` – any string; must match the verify token you set
     when configuring the webhook in the Meta Developer dashboard
   * `SPOND_USER` / `SPOND_PASS` – the username and password of a Spond
     account with access to your club or team
   * `DAYS_AHEAD` – how many days into the future to fetch events when
     inviting players (default: 14)

4. **Run the server** locally:

   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8080
   ```

   You can test webhook verification by visiting `http://localhost:8080/whatsapp/webhook?hub.verify_token=...&hub.challenge=1234`.

5. **Deploy**. On Render, create a new web service connected to your repo.
   Use the build command `pip install -r requirements.txt` and the run
   command `uvicorn app:app --host 0.0.0.0 --port $PORT`. Set the same
   environment variables you used locally.

6. **Configure your WhatsApp Business App**. In the Meta Developer
   dashboard:

   * Set your webhook **callback URL** to `https://<your-app>.onrender.com/whatsapp/webhook`.
   * Use the same **verify token** you set in `.env`.
   * Subscribe to the **messages** field for WhatsApp business accounts.

7. **Trigger invites**. Use a scheduler or manual HTTP call to
   `/sync-and-invite`. The endpoint fetches upcoming events and sends
   messages to invitees. On Render you can add a Cron job that
   periodically triggers this endpoint using `curl`.

Limitations and warnings
------------------------

* The Spond integration uses an **unofficial** API. This means it
  could break if Spond changes their endpoints or authentication.
* You must maintain a mapping of phone numbers to Spond `person_id`.
  This is handled automatically by `db.py` when invites are sent, but if
  numbers are missing from Spond your players will need to link their
  numbers manually.
* WhatsApp Business policies require template messages when starting a
  conversation outside a 24‑hour window. If you choose to initiate
  conversations, register a template and send it first.

Credits
-------

This bridge was inspired by reverse‑engineering efforts of the Spond
community and leverages the `spond` library available on PyPI. The
WhatsApp integration uses the Cloud API as documented by Meta.