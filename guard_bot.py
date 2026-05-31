# guard_bot.py – full code (copy everything below)
import os
import json
import asyncio
from datetime import datetime, time, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, ChatPermissions, ChatMember
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "Guard Bot is running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port)

Thread(target=run_flask, daemon=True).start()

BOT_TOKEN = os.environ.get('GUARD_BOT_TOKEN', '8749080890:AAFsN_CFjesHnqTFAcOAwslPyjnXDXihx4M')
DATA_FILE = "guard_bot_data.json"
DEFAULT_NIGHT_ON = "01:00"
DEFAULT_NIGHT_OFF = "07:00"
SPAM_WINDOW = 5
SPAM_MAX_MSGS = 5
MUTE_DURATION = 300

data = {}
data_lock = asyncio.Lock()
msg_tracker = {}

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    else:
        data = {}

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_chat_settings(chat_id):
    chat_id_str = str(chat_id)
    if chat_id_str not in data:
        data[chat_id_str] = {
            "night_mode": False,
            "night_on": DEFAULT_NIGHT_ON,
            "night_off": DEFAULT_NIGHT_OFF,
            "anti_spam": False,
            "force_join_channels": [],
        }
    return data[chat_id_str]

async def is_group_admin(update, user_id):
    chat = update.effective_chat
    if chat.type not in ["group", "supergroup"]:
        return False
    try:
        member = await chat.get_member(user_id)
        return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except:
        return False

async def is_user_joined_required_channels(chat_id, user_id, bot):
    settings = get_chat_settings(chat_id)
    channels = settings.get("force_join_channels", [])
    if not channels:
        return True
    for channel in channels:
        try:
            chat_member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER):
                return False
        except:
            return False
    return True

async def mute_user(chat_id, user_id, until_date, bot):
    permissions = ChatPermissions(can_send_messages=False)
    await bot.restrict_chat_member(chat_id, user_id, permissions, until_date=until_date)

async def auto_night_scheduler(bot):
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        for chat_id_str, settings in list(data.items()):
            chat_id = int(chat_id_str)
            night_on = settings.get("night_on", DEFAULT_NIGHT_ON)
            night_off = settings.get("night_off", DEFAULT_NIGHT_OFF)
            should_be_on = (night_on <= current_time < night_off)
            if night_on > night_off:
                should_be_on = (current_time >= night_on or current_time < night_off)
            if should_be_on and not settings.get("night_mode", False):
                settings["night_mode"] = True
                save_data()
                try:
                    await bot.send_message(chat_id, "🌙 Auto Night Mode Enabled")
                except:
                    pass
            elif not should_be_on and settings.get("night_mode", False):
                settings["night_mode"] = False
                save_data()
                try:
                    await bot.send_message(chat_id, "☀️ Auto Night Mode Disabled")
                except:
                    pass
        await asyncio.sleep(60)

async def nighton(update, context):
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("⚠️ Only group admins can use this command.")
        return
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    settings["night_mode"] = True
    save_data()
    await update.message.reply_text("🌙 Night Mode Enabled")

async def nightoff(update, context):
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("⚠️ Only group admins can use this command.")
        return
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    settings["night_mode"] = False
    save_data()
    await update.message.reply_text("☀️ Night Mode Disabled")

async def setnight(update, context):
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("⚠️ Only group admins can use this command.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /setnight 01:00 07:00")
        return
    on_time, off_time = context.args[0], context.args[1]
    try:
        datetime.strptime(on_time, "%H:%M")
        datetime.strptime(off_time, "%H:%M")
    except:
        await update.message.reply_text("Invalid time format. Use HH:MM")
        return
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    settings["night_on"] = on_time
    settings["night_off"] = off_time
    save_data()
    await update.message.reply_text(f"✅ Auto night times set: ON {on_time}, OFF {off_time} IST")

async def info(update, context):
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("⚠️ Only group admins can use this command.")
        return
    target_user = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif context.args:
        username = context.args[0].lstrip('@')
        try:
            target_user = await context.bot.get_chat_member(update.effective_chat.id, f"@{username}")
            target_user = target_user.user
        except:
            pass
    if not target_user:
        await update.message.reply_text("Reply to a user or use /info @username")
        return
    member = await update.effective_chat.get_member(target_user.id)
    status = member.status
    status_str = {
        ChatMember.CREATOR: "Creator",
        ChatMember.ADMINISTRATOR: "Administrator",
        ChatMember.MEMBER: "Member",
    }.get(status, "Other")
    msg = f"👤 User Info\n🆔 ID: {target_user.id}\n📛 Name: {target_user.first_name or ''}\n👤 Username: @{target_user.username or 'N/A'}\n🔗 [link](tg://user?id={target_user.id})\n📌 Status: {status_str}"
    await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)

async def antispamon(update, context):
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("⚠️ Only group admins can use this command.")
        return
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    settings["anti_spam"] = True
    save_data()
    await update.message.reply_text("🛡️ Anti‑Spam Enabled")

async def antispamoff(update, context):
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("⚠️ Only group admins can use this command.")
        return
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    settings["anti_spam"] = False
    save_data()
    await update.message.reply_text("✅ Anti‑Spam Disabled")

async def forcejoin(update, context):
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("⚠️ Only group admins can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /forcejoin @channel1 @channel2")
        return
    channels = [ch for ch in context.args if ch.startswith('@')]
    if not channels:
        await update.message.reply_text("Give valid channel usernames starting with @")
        return
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    settings["force_join_channels"] = list(set(channels))
    save_data()
    await update.message.reply_text(f"✅ Force‑join channels set: {', '.join(channels)}")

async def forcejoin_remove(update, context):
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("⚠️ Only group admins can use this command.")
        return
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    settings["force_join_channels"] = []
    save_data()
    await update.message.reply_text("✅ Force‑join requirement removed.")

async def forcejoin_list(update, context):
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("⚠️ Only group admins can use this command.")
        return
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    channels = settings.get("force_join_channels", [])
    if channels:
        await update.message.reply_text(f"📢 Force‑join channels: {', '.join(channels)}")
    else:
        await update.message.reply_text("No force‑join channels set.")

async def guard_message(update, context):
    if not update.message:
        return
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ["group", "supergroup"]:
        return
    if user.id == context.bot.id:
        return
    chat_id = chat.id
    user_id = user.id
    settings = get_chat_settings(chat_id)
    # Night mode delete
    if settings.get("night_mode", False):
        if not await is_group_admin(update, user_id):
            try:
                await update.message.delete()
                return
            except:
                pass
    # Force join check
    if not await is_group_admin(update, user_id):
        channels = settings.get("force_join_channels", [])
        if channels:
            joined = await is_user_joined_required_channels(chat_id, user_id, context.bot)
            if not joined:
                try:
                    await update.message.delete()
                    await context.bot.send_message(chat_id, f"@{user.username or user.first_name}, you must join {', '.join(channels)} to talk here.")
                    return
                except:
                    pass
    # Anti-spam
    if settings.get("anti_spam", False):
        key = (chat_id, user_id)
        now = datetime.now().timestamp()
        if key not in msg_tracker:
            msg_tracker[key] = []
        msg_tracker[key] = [t for t in msg_tracker[key] if now - t < SPAM_WINDOW]
        msg_tracker[key].append(now)
        if len(msg_tracker[key]) > SPAM_MAX_MSGS:
            until = datetime.now() + timedelta(seconds=MUTE_DURATION)
            permissions = ChatPermissions(can_send_messages=False)
            await context.bot.restrict_chat_member(chat_id, user_id, permissions, until_date=until)
            await context.bot.send_message(chat_id, f"🚫 {user.mention_html()} muted for 5 min (spam)", parse_mode='HTML')
            try:
                await update.message.delete()
            except:
                pass
            msg_tracker[key] = []
            return

async def post_init(app):
    load_data()
    asyncio.create_task(auto_night_scheduler(app.bot))

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.post_init = post_init
    app.add_handler(CommandHandler("nighton", nighton))
    app.add_handler(CommandHandler("nightoff", nightoff))
    app.add_handler(CommandHandler("setnight", setnight))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("antispamon", antispamon))
    app.add_handler(CommandHandler("antispamoff", antispamoff))
    app.add_handler(CommandHandler("forcejoin", forcejoin))
    app.add_handler(CommandHandler("forcejoin_remove", forcejoin_remove))
    app.add_handler(CommandHandler("forcejoin_list", forcejoin_list))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, guard_message), group=1)
    print("🛡️ Guard Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
