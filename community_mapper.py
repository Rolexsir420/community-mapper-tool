import asyncio
import csv
import io
import os
from datetime import datetime

import pytz
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

load_dotenv()

IST = pytz.timezone("Asia/Kolkata")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL"))
PRIMARY_GROUP = int(os.getenv("PRIMARY_GROUP"))
SCAN_LIMIT = int(os.getenv("SCAN_LIMIT", 3000))

app = Client(
    "mapper",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

MY_ID = None  # will be set on startup

# ── startup confirmation ──────────────────────────────────────────────
async def on_start(client: Client):
    global MY_ID
    try:
        me = await client.get_me()
        MY_ID = me.id  # store your own ID

        async for dialog in client.get_dialogs():
            pass

        await client.send_message(LOG_CHANNEL,
            f"✅ **Community Mapper Online**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Account : {me.first_name}\n"
            f"🆔 UID     : `{me.id}`\n"
            f"🕐 Time    : {datetime.now(IST).strftime('%d %b %Y, %H:%M IST')}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    except Exception as e:
        print(f"Startup error: {e}")

# ── fetch senders with full deduplication ─────────────────────────────
async def fetch_senders(client: Client, group_id: int, limit: int) -> dict:
    found_users = {}
    processed_ids = set()

    try:
        chat_info = await client.get_chat(group_id)
        chat_title = chat_info.title
        chat_url = f"https://t.me/{chat_info.username}" if chat_info.username else None
    except Exception:
        await client.send_message(LOG_CHANNEL,
            f"❌ Cannot access group `{group_id}` — skipping")
        return {}

    try:
        async for item in client.get_chat_history(group_id, limit=limit):

            if not item.from_user or not item.from_user.id:
                continue

            sender = item.from_user
            sender_id = sender.id

            if sender_id in processed_ids:
                continue

            if sender.is_bot:
                continue

            if not
