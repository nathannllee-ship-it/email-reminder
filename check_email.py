#!/usr/bin/env python3
"""Daily email reminder: check Gmail for unread from important senders, push to Telegram.

Runs in two modes:
- Local:  does a one-time browser OAuth, caches token to token.json
- CI:     reads OAuth token JSON from env var GMAIL_TOKEN_JSON (no browser)
"""
import os
import json
import urllib.request
import urllib.parse

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Telegram (env overrides; falls back to the values set up in this session)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8728830447:AAE4Bth9NtP1UbwOQakca7VpAo4N-Y1YdwI")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT", "6623152180")

CLIENT_SECRET = os.environ.get(
    "GMAIL_CLIENT_SECRET_FILE",
    "/Users/nhlee/Downloads/client_secret_296568091127-v7jqbl6gt4q0jlikv0blinapp51vt7bv.apps.googleusercontent.com.json",
)
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")

# Only count unread that arrived in the last day (actionable daily digest).
WINDOW = os.environ.get("EMAIL_WINDOW", "newer_than:1d")

# label -> Gmail search query (WINDOW prepended below)
_SENDERS = {
    "Mercor": "from:mercor.com",
    "Snorkel": "from:snorkel.ai",
    "LinkedIn messages": "(from:messages-noreply@linkedin.com OR from:messaging-digest-noreply@linkedin.com)",
    "LinkedIn invitations": "from:invitations@linkedin.com",
    "PNC": "from:pnc.com",
    "PayPal": "from:paypal.com",
    "Kraken": "from:kraken.com",
    "Security alerts": "{from:accounts.google.com from:mail.instagram.com from:security-noreply@linkedin.com}",
    "School (.edu)": "from:.edu",
}
SEARCHES = {k: f"in:inbox is:unread {WINDOW} {v}" for k, v in _SENDERS.items()}


def get_credentials():
    # CI mode: token JSON provided via env
    token_json = os.environ.get("GMAIL_TOKEN_JSON")
    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    # Local mode: cached token, else browser flow
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def count_unread(service, query, cap=100):
    """Accurate count by paging through message IDs, capped (shows '<cap>+')."""
    total = 0
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=100, pageToken=page_token
        ).execute()
        total += len(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token or total >= cap:
            break
    return total


def build_message(counts):
    hits = {k: v for k, v in counts.items() if v > 0}
    if not hits:
        return "✅ Inbox clear — no important unread emails."
    lines = ["📬 End of Day Email Check"]
    for label, n in hits.items():
        lines.append(f"• {label} — {n} unread")
    return "\n".join(lines)


def send_telegram(text):
    data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=data
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        print("Telegram status:", r.status)


def main():
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)
    counts = {}
    for label, query in SEARCHES.items():
        try:
            counts[label] = count_unread(service, query)
        except Exception as e:
            print(f"search failed [{label}]: {e}")
            counts[label] = 0
        print(f"{label}: {counts[label]}")
    msg = build_message(counts)
    print("---\n" + msg + "\n---")
    send_telegram(msg)


if __name__ == "__main__":
    main()
