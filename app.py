import os
import asyncio
import time
from telethon import TelegramClient, events
from telethon.errors import ChatAdminRequiredError

# ───── ENV SETUP ───── #
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

# ───── LOAD INITIAL CHATS ───── #
def load_initial_chats():
    seeded_chats = set()
    raw_value = os.environ.get("TRACKED_CHAT_IDS")
    if not raw_value:
        return seeded_chats
    for raw_id in raw_value.split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        try:
            seeded_chats.add(int(raw_id))
        except ValueError:
            print(f"⚠️ Could not parse chat id '{raw_id}' from TRACKED_CHAT_IDS.")
    return seeded_chats

tracked_chats.update(load_initial_chats())

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

# ───── RIGHTS CHECK LOOP ───── #
async def check_rights_loop():
    while True:
        try:
            rights_groups = []
            newly_eligible = []

            for chat_id in list(tracked_chats):
                try:
                    entity = await bot.get_entity(chat_id)
                    perms = await bot.get_permissions(entity.id, "me")

                    if perms.is_admin and perms.ban_users:
                        rights_groups.append(entity)

                        if entity.id not in cleaned_chats and entity.id not in active_cleanup_tasks:
                            task = asyncio.create_task(remove_all_members(entity))
                            active_cleanup_tasks[entity.id] = task
                            newly_eligible.append(entity.title)

                except Exception as e:
                    if chat_id not in error_chats:
                        await bot.send_message(
                            LOG_GROUP_ID,
                            f"⚠️ Error checking rights in chat `{chat_id}`: {e}"
                        )
                        error_chats.add(chat_id)

            if newly_eligible:
                msg = "🔍 Newly eligible groups with ban rights:\n" + "\n".join(f"• {title}" for title in newly_eligible)
                await bot.send_message(LOG_GROUP_ID, msg)

        except Exception as e:
            await bot.send_message(LOG_GROUP_ID, f"⚠️ Global error in rights loop: {e}")

        await asyncio.sleep(10)

# ───── EVENT: Bot Added to New Group ───── #
@bot.on(events.ChatAction)
async def on_added(event):
    if event.user_added and event.user_id == (await bot.get_me()).id:
        chat = await event.get_chat()
        tracked_chats.add(chat.id)
        await bot.send_message(
            LOG_GROUP_ID,
            f"🆕 Added to new group/channel: **{chat.title}** (`{chat.id}`)\nWill check ban rights in next cycle."
        )

# ───── EVENT: Track Messages ───── #
@bot.on(events.NewMessage())
async def track_message_chats(event):
    if event.is_group or event.is_channel:
        chat = await event.get_chat()
        if hasattr(chat, "id"):
            tracked_chats.add(chat.id)

# ───── /start COMMAND ───── #
@bot.on(events.NewMessage(pattern="/start"))
async def start_cmd(event):
    if event.is_private:
        await event.respond(
            "🤖 Bot is running.\n\n"
            "👁️ Auto-monitoring groups/channels for ban rights.\n"
            "🧹 Will auto-remove users silently if permitted."
        )

# ───── MAIN LOOP ───── #
async def main():
    await bot.send_message(
        LOG_GROUP_ID,
        "✅ Bot started successfully!\n"
        "📡 Monitoring groups/channels every 10s...\n"
        "💡 Tip: preload chats with TRACKED_CHAT_IDS env var (comma separated IDs)."
    )
    await check_rights_loop()

# ───── ENTRY ───── #
print("🤖 Auto Rights Monitor Bot running...")
bot.loop.run_until_complete(main())
