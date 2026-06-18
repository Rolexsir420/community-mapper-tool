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

        # force Pyrogram to learn all channels/groups before sending
        async for dialog in client.get_dialogs():
            pass  # just iterate all — builds peer cache

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

            if not sender.first_name and not sender.username:
                continue

            processed_ids.add(sender_id)
            found_users[sender_id] = {
                "uid": sender_id,
                "username": sender.username or "N/A",
                "name": f"{sender.first_name or ''} {sender.last_name or ''}".strip(),
                "group_name": chat_title,
                "group_id": group_id,
                "group_link": chat_url
            }

            await asyncio.sleep(0.05)

    except FloodWait as fw:
        await asyncio.sleep(fw.value + 2)
        return await fetch_senders(client, group_id, limit)

    except Exception as err:
        await client.send_message(LOG_CHANNEL,
            f"⚠️ Error scanning `{group_id}`: {err}")
        return {}

    if not found_users:
        await client.send_message(LOG_CHANNEL,
            f"⚠️ `{chat_title}` returned no data — empty or restricted")

    return found_users

# ── staggered parallel scanning ───────────────────────────────────────
async def run_parallel_scan(client: Client, chat_ids: list, msg_limit: int) -> list:
    job_list = []
    for idx, cid in enumerate(chat_ids):
        await asyncio.sleep(idx * 2)
        job_list.append(fetch_senders(client, cid, msg_limit))
    scan_results = await asyncio.gather(*job_list)
    return scan_results

# ── send individual fresh member log with serial number ───────────────
async def post_member_log(client: Client, member: dict, count: int):
    profile_url = f"tg://user?id={member['uid']}"

    if member["group_link"]:
        chat_mention = f"[{member['group_name']}]({member['group_link']})"
    else:
        chat_mention = f"[{member['group_name']}](tg://chat?id={member['group_id']})"

    await client.send_message(LOG_CHANNEL,
        f"🎯 **#{count} FRESH MEMBER**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Name    : [{member['name']}]({profile_url})\n"
        f"🔖 Username: @{member['username']}\n"
        f"🆔 UID     : `{member['uid']}`\n"
        f"📢 Group   : {chat_mention}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        disable_web_page_preview=True
    )
    await asyncio.sleep(0.3)

# ── send CSV to log channel ───────────────────────────────────────────
async def deliver_csv(client: Client, records: list, fname: str):
    if not records:
        return
    buffer = io.StringIO()
    sheet = csv.DictWriter(buffer,
        fieldnames=["serial", "uid", "username", "name", "group_name", "group_link"])
    sheet.writeheader()
    for idx, member in enumerate(records, start=1):
        sheet.writerow({
            "serial": idx,
            "uid": member["uid"],
            "username": member["username"],
            "name": member["name"],
            "group_name": member["group_name"],
            "group_link": member["group_link"] or "N/A"
        })
    buffer.seek(0)
    file_bytes = io.BytesIO(buffer.read().encode())
    file_bytes.name = fname
    await client.send_document(LOG_CHANNEL, file_bytes,
        caption=f"📁 {fname} — {len(records)} fresh members")

# ── .scan command ─────────────────────────────────────────────────────
@app.on_message(filters.command("scan", prefixes=".") & filters.me)
async def handle_scan(client: Client, message: Message):
    input_args = message.command[1:]
    if not input_args:
        await message.reply(
            "**Usage:** `.scan -100xxx -100yyy -100zzz`\n"
            "Scans all given groups and finds fresh members not in your primary group."
        )
        return

    try:
        target_groups = [int(a) for a in input_args]
    except ValueError:
        await message.reply("❌ Invalid group IDs. Use numeric IDs only.")
        return

    start_time = datetime.now(IST).strftime("%d %b %Y, %H:%M IST")
    await client.send_message(LOG_CHANNEL,
        f"🔄 **SCAN STARTED**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 Groups to scan : {len(target_groups)}\n"
        f"📩 Limit per group: {SCAN_LIMIT} messages\n"
        f"🕐 Time           : {start_time}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    # scan primary + all secondary with stagger
    all_chat_ids = [PRIMARY_GROUP] + target_groups
    all_scan_data = await run_parallel_scan(client, all_chat_ids, SCAN_LIMIT)

    # primary is first result
    base_uids = set(all_scan_data[0].keys())

    # merge secondary — no duplicate UIDs across groups
    merged_targets = {}
    for scan_result in all_scan_data[1:]:
        for uid, member in scan_result.items():
            if uid not in merged_targets:
                merged_targets[uid] = member

    # find fresh — in secondary but NOT in primary
    new_members = [
        member for uid, member in merged_targets.items()
        if uid not in base_uids
    ]

    # per group breakdown for summary
    breakdown_map = {}
    for scan_result in all_scan_data[1:]:
        for uid, member in scan_result.items():
            gname = member["group_name"]
            glink = member["group_link"]
            if gname not in breakdown_map:
                breakdown_map[gname] = {"count": 0, "link": glink}
            breakdown_map[gname]["count"] += 1

    breakdown_lines = ""
    for gname, info in breakdown_map.items():
        if info["link"]:
            breakdown_lines += f"   • [{gname}]({info['link']}) — {info['count']}\n"
        else:
            breakdown_lines += f"   • {gname} — {info['count']}\n"

    end_time = datetime.now(IST).strftime("%d %b %Y, %H:%M IST")

    # send summary
    await client.send_message(LOG_CHANNEL,
        f"✅ **SCAN COMPLETE**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔵 Your Group Members : {len(base_uids)}\n"
        f"🟢 Groups Scanned     : {len(target_groups)}\n"
        f"{breakdown_lines}"
        f"🎯 Fresh Members      : {len(new_members)}\n"
        f"🕐 Time               : {end_time}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        disable_web_page_preview=True
    )

    # smart threshold
    if len(new_members) <= 30:
        for serial_no, member in enumerate(new_members, start=1):
            await post_member_log(client, member, serial_no)
    else:
        await client.send_message(LOG_CHANNEL,
            f"📋 {len(new_members)} fresh members found — sending CSV only to keep channel clean")

    # always send CSV
    await deliver_csv(
        client, new_members,
        f"fresh_members_{datetime.now(IST).strftime('%d%m%Y_%H%M')}.csv"
    )

# ── entry point ───────────────────────────────────────────────────────
async def launch():
    async with app:
        await on_start(app)
        await asyncio.Event().wait()

asyncio.run(launch())
