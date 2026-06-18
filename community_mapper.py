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

# ── startup confirmation ──────────────────────────────────────────────
async def on_start(client: Client):
    try:
        me = await client.get_me()
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
    members = {}
    seen_uids = set()

    # validate group access + fetch group info
    try:
        chat = await client.get_chat(group_id)
        group_name = chat.title
        group_link = f"https://t.me/{chat.username}" if chat.username else None
    except Exception:
        await client.send_message(LOG_CHANNEL,
            f"❌ Cannot access group `{group_id}` — skipping")
        return {}

    try:
        async for msg in client.get_chat_history(group_id, limit=limit):

            # bulletproof null check
            if not msg.from_user or not msg.from_user.id:
                continue

            u = msg.from_user
            uid = u.id

            # skip already seen UID
            if uid in seen_uids:
                continue

            # skip bots
            if u.is_bot:
                continue

            # skip deleted accounts
            if not u.first_name and not u.username:
                continue

            # first time — mark and store
            seen_uids.add(uid)
            members[uid] = {
                "uid": uid,
                "username": u.username or "N/A",
                "name": f"{u.first_name or ''} {u.last_name or ''}".strip(),
                "group_name": group_name,
                "group_id": group_id,
                "group_link": group_link
            }

            await asyncio.sleep(0.05)

    except FloodWait as e:
        await asyncio.sleep(e.value + 2)
        return await fetch_senders(client, group_id, limit)

    except Exception as ex:
        await client.send_message(LOG_CHANNEL,
            f"⚠️ Error scanning `{group_id}`: {ex}")
        return {}

    # empty group warning
    if not members:
        await client.send_message(LOG_CHANNEL,
            f"⚠️ [`{group_name}`]({group_link}) returned no data — empty or restricted",
            disable_web_page_preview=True
        )

    return members

# ── staggered parallel scanning ───────────────────────────────────────
async def scan_multiple(client: Client, group_ids: list, limit: int) -> list:
    tasks = []
    for i, gid in enumerate(group_ids):
        await asyncio.sleep(i * 2)  # 2s stagger
        tasks.append(fetch_senders(client, gid, limit))
    results = await asyncio.gather(*tasks)
    return results

# ── send individual fresh member log with serial number ───────────────
async def send_fresh_log(client: Client, user: dict, serial: int):
    profile_link = f"tg://user?id={user['uid']}"

    if user["group_link"]:
        group_mention = f"[{user['group_name']}]({user['group_link']})"
    else:
        group_mention = f"[{user['group_name']}](tg://chat?id={user['group_id']})"

    await client.send_message(LOG_CHANNEL,
        f"🎯 **#{serial} FRESH MEMBER**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Name    : [{user['name']}]({profile_link})\n"
        f"🔖 Username: @{user['username']}\n"
        f"🆔 UID     : `{user['uid']}`\n"
        f"📢 Group   : {group_mention}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        disable_web_page_preview=True
    )
    await asyncio.sleep(0.3)

# ── send CSV to log channel ───────────────────────────────────────────
async def send_csv(client: Client, data: list, filename: str):
    if not data:
        return
    output = io.StringIO()
    writer = csv.DictWriter(output,
        fieldnames=["serial", "uid", "username", "name", "group_name", "group_link"])
    writer.writeheader()
    for i, user in enumerate(data, start=1):
        writer.writerow({
            "serial": i,
            "uid": user["uid"],
            "username": user["username"],
            "name": user["name"],
            "group_name": user["group_name"],
            "group_link": user["group_link"] or "N/A"
        })
    output.seek(0)
    bio = io.BytesIO(output.read().encode())
    bio.name = filename
    await client.send_document(LOG_CHANNEL, bio,
        caption=f"📁 {filename} — {len(data)} fresh members")

# ── .scan command ─────────────────────────────────────────────────────
@app.on_message(filters.command("scan", prefixes=".") & filters.me)
async def cmd_scan(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        await message.reply(
            "**Usage:** `.scan -100xxx -100yyy -100zzz`\n"
            "Scans all given groups and finds fresh members not in your primary group."
        )
        return

    try:
        secondary_groups = [int(a) for a in args]
    except ValueError:
        await message.reply("❌ Invalid group IDs. Use numeric IDs only.")
        return

    now = datetime.now(IST).strftime("%d %b %Y, %H:%M IST")
    await client.send_message(LOG_CHANNEL,
        f"🔄 **SCAN STARTED**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 Groups to scan : {len(secondary_groups)}\n"
        f"📩 Limit per group: {SCAN_LIMIT} messages\n"
        f"🕐 Time           : {now}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    # scan primary + all secondary with stagger
    all_group_ids = [PRIMARY_GROUP] + secondary_groups
    all_results = await scan_multiple(client, all_group_ids, SCAN_LIMIT)

    # primary is first result
    primary_uids = set(all_results[0].keys())

    # merge secondary — no duplicate UIDs across groups
    secondary_combined = {}
    for result in all_results[1:]:
        for uid, user in result.items():
            if uid not in secondary_combined:
                secondary_combined[uid] = user

    # find fresh — in secondary but NOT in primary
    fresh = [
        user for uid, user in secondary_combined.items()
        if uid not in primary_uids
    ]

    # per group breakdown for summary
    group_breakdown = {}
    for result in all_results[1:]:
        for uid, user in result.items():
            gname = user["group_name"]
            glink = user["group_link"]
            if gname not in group_breakdown:
                group_breakdown[gname] = {"count": 0, "link": glink}
            group_breakdown[gname]["count"] += 1

    breakdown_text = ""
    for gname, info in group_breakdown.items():
        if info["link"]:
            breakdown_text += f"   • [{gname}]({info['link']}) — {info['count']}\n"
        else:
            breakdown_text += f"   • {gname} — {info['count']}\n"

    now2 = datetime.now(IST).strftime("%d %b %Y, %H:%M IST")

    # send summary
    await client.send_message(LOG_CHANNEL,
        f"✅ **SCAN COMPLETE**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔵 Your Group Members : {len(primary_uids)}\n"
        f"🟢 Groups Scanned     : {len(secondary_groups)}\n"
        f"{breakdown_text}"
        f"🎯 Fresh Members      : {len(fresh)}\n"
        f"🕐 Time               : {now2}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        disable_web_page_preview=True
    )

    # smart threshold — individual logs only if small result
    if len(fresh) <= 30:
        for serial, user in enumerate(fresh, start=1):
            await send_fresh_log(client, user, serial)
    else:
        await client.send_message(LOG_CHANNEL,
            f"📋 {len(fresh)} fresh members found — sending CSV only to keep channel clean")

    # always send CSV
    await send_csv(
        client, fresh,
        f"fresh_members_{datetime.now(IST).strftime('%d%m%Y_%H%M')}.csv"
    )

# ── entry point ───────────────────────────────────────────────────────
async def main():
    async with app:
        await on_start(app)
        await asyncio.Event().wait()

asyncio.run(main())
