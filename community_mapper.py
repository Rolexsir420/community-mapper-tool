from pyrogram import Client
import os
from dotenv import load_dotenv

print("STARTING BOT...", flush=True)

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL"))

app = Client(
    "test",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

try:
    with app:
        me = app.get_me()

        print(f"LOGGED IN AS: {me.first_name} ({me.id})", flush=True)

        app.send_message(
            LOG_CHANNEL,
            "✅ Railway Test Successful"
        )

        print("MESSAGE SENT SUCCESSFULLY", flush=True)

except Exception as e:
    print("ERROR:", repr(e), flush=True)
    raise
