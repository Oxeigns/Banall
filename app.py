import os
import asyncio
import time
from telethon import TelegramClient, events, functions, types
from telethon.errors import FloodWaitError, ChatAdminRequiredError, UserAdminInvalidError

# ───── ENV CONFIG ───── #
def get_env_var(name):
    value = os.environ.get(name)
    if not value:
        print(f"⚠️ Missing: {name}")
    return value

def to_int(value):
    try: return int(value)
    except: return None

BOT_TOKEN = get_env_var("BOT_TOKEN")
API_ID = to_int(get_env_var("API_ID"))
API_HASH = get_env_var("API_HASH")
LOG_GROUP_ID = to_int(get_env_var("LOG_GROUP_ID"))

# Adjust BATCH_SIZE based on your bot's limits (20-30 is usually safe)
BATCH_SIZE = 25 

bot = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

active_tasks = set()

# ───── ATOMIC KICK FUNCTION ───── #
async def fast_kick(chat_id, user_id):
    """The fastest way to remove a user using raw RPC."""
    try:
        await bot(functions.channels.EditBannedRequest(
            channel=chat_id,
            participant=user_id,
            banned_rights=types.ChatBannedRights(until_date=None, view_messages=True)
        ))
        return True
    except FloodWaitError as e:
        print(f"🛑 Rate limited! Sleeping for {e.seconds}s")
        await asyncio.sleep(e.seconds)
        return False
    except (UserAdminInvalidError, ChatAdminRequiredError):
        return "stop" # Signal to stop the whole process
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

    await bot.send_message(LOG_GROUP_ID, f"⚡ **High-Speed Purge Started**\nGroup: {chat.title}")

    try:
        # iter_participants is a generator; it doesn't wait for the whole list to load
        current_batch = []
        async for user in bot.iter_participants(chat.id):
            if user.id == me.id: continue
            
            # Add to batch
            current_batch.append(fast_kick(chat.id, user.id))

            if len(current_batch) >= BATCH_SIZE:
                # Execute batch concurrently
                results = await asyncio.gather(*current_batch)
                
                removed_count += sum(1 for r in results if r is True)
                current_batch = []
                
                if "stop" in results:
                    await bot.send_message(LOG_GROUP_ID, f"❌ **Aborted:** Permissions lost in {chat.title}")
                    break
                
                # Small yield to the event loop
                await asyncio.sleep(0.1)

        # Catch remaining users in the last batch
        if current_batch:
            results = await asyncio.gather(*current_batch)
            removed_count += sum(1 for r in results if r is True)

    finally:
        duration = round(time.time() - start_time, 2)
        await bot.send_message(
            LOG_GROUP_ID, 
            f"🏁 **Purge Complete**\nGroup: {chat.title}\nRemoved: {removed_count}\nTime: {duration}s"
        )
        active_tasks.remove(chat.id)

# ───── EVENTS ───── #
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

# ───── MAIN ───── #
async def main():
    print("🚀 Turbo-Bot is Online")
    await bot.send_message(LOG_GROUP_ID, "🚀 **Bot Online:** Monitoring for targets...")
    await bot.run_until_disconnected()

bot.loop.run_until_complete(main())
