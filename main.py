import os
import sys
import asyncio
import logging
from datetime import datetime

import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession

API_ID        = int(os.environ.get("API_ID", 0))
API_HASH      = os.environ.get("API_HASH", "")
SESSION_STR   = os.environ.get("SESSION_STRING", "")
BOT_TOKEN     = os.environ.get("BOT_TOKEN", "")
TIMEZONE      = os.environ.get("TIMEZONE", "Asia/Tehran")
TIME_FORMAT   = os.environ.get("TIME_FORMAT", "%H:%M")
UPDATE_EVERY  = int(os.environ.get("UPDATE_INTERVAL", "60"))
BASE_NAME     = os.environ.get("BASE_NAME", "")
SEPARATOR     = os.environ.get("SEPARATOR", " ǀ ")
OWNER_ID      = int(os.environ.get("OWNER_ID", "0"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("selfbot")

setup_sessions = {}


async def run_setup_bot():
    log.info("حالت ستاپ فعال شد")
    bot = TelegramClient("setup_bot", API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)

    me = await bot.get_me()
    log.info(f"ربات ستاپ: @{me.username}")

    @bot.on(events.NewMessage(pattern=r"/start"))
    async def start_handler(event):
        global OWNER_ID
        uid = event.sender_id
        if OWNER_ID == 0:
            OWNER_ID = uid
        if uid != OWNER_ID:
            await event.respond("⛔ فقط مالک ربات.")
            return
        setup_sessions[uid] = {"step": "phone", "phone": ""}
        await event.respond(
            "🔧 **ساخت Session String**\n\n"
            "شماره تلفنت رو بفرست:\n"
            "مثال: `+989123456789`"
        )

    @bot.on(events.NewMessage(func=lambda e: e.sender_id == OWNER_ID))
    async def msg_handler(event):
        uid = event.sender_id
        if uid not in setup_sessions:
            return
        s = setup_sessions[uid]
        text = event.text.strip()

        if s["step"] == "phone":
            if not text.startswith("+") or len(text) < 10:
                await event.respond("❌ فرمت اشتباه. مثال: `+989123456789`")
                return
            s["phone"] = text
            s["step"] = "code"
            s["client"] = TelegramClient(StringSession(), API_ID, API_HASH)
            await s["client"].connect()
            try:
                sent = await s["client"].send_code_request(text)
                s["hash"] = sent.phone_code_hash
                await event.respond("📨 کد تایید رو بفرست:")
            except Exception as e:
                s["step"] = "phone"
                await event.respond(f"❌ خطا: `{e}`\nدوباره شماره بفرست.")

        elif s["step"] == "code":
            code = text.replace(" ", "")
            if not code.isdigit():
                await event.respond("❌ کد باید عددی باشه.")
                return
            try:
                await s["client"].sign_in(
                    phone=s["phone"],
                    code=code,
                    phone_code_hash=s["hash"]
                )
            except Exception as e:
                if "password" in str(e).lower():
                    s["step"] = "2fa"
                    await event.respond("🔒 رمز دو مرحله‌ای رو بفرست:")
                    return
                s["step"] = "phone"
                await event.respond(f"❌ خطا: `{e}`\n/start رو بزن.")
                return

            ss = s["client"].session.save()
            await s["client"].disconnect()
            await event.respond(
                "✅ **سشن ساخته شد!**\n\n"
                f"`{ss}`\n\n"
                "1. Railway → Variables\n"
                "2. `SESSION_STRING` = اون رشته\n"
                "3. ری‌دیپلوی کن 🚀"
            )
            del setup_sessions[uid]

        elif s["step"] == "2fa":
            try:
                await s["client"].sign_in(password=text)
                ss = s["client"].session.save()
                await s["client"].disconnect()
                await event.respond(
                    "✅ **سشن ساخته شد!**\n\n"
                    f"`{ss}`\n\n"
                    "1. Railway → Variables\n"
                    "2. `SESSION_STRING` = اون رشته\n"
                    "3. ری‌دیپلوی کن 🚀"
                )
                del setup_sessions[uid]
            except Exception as e:
                await event.respond(f"❌ رمز اشتباه: `{e}`")

    await bot.run_until_disconnected()


original_first_name = ""
original_last_name  = ""
original_about      = ""


def get_time_string():
    return datetime.now(pytz.timezone(TIMEZONE)).strftime(TIME_FORMAT)


async def update_name(client):
    global original_first_name, original_last_name, original_about
    try:
        from telethon.tl.functions.account import UpdateProfileRequest
        base = BASE_NAME if BASE_NAME else original_first_name
        name = f"{base}{SEPARATOR}{get_time_string()}"
        await client(UpdateProfileRequest(
            first_name=name,
            last_name=original_last_name,
            about=original_about,
        ))
        log.info(f"اسم آپدیت شد: {name}")
    except Exception as e:
        log.error(f"خطا: {e}")


async def restore_name(client):
    global original_first_name, original_last_name, original_about
    try:
        from telethon.tl.functions.account import UpdateProfileRequest
        await client(UpdateProfileRequest(
            first_name=original_first_name,
            last_name=original_last_name,
            about=original_about,
        ))
    except Exception as e:
        log.error(f"خطا: {e}")


async def run_selfbot():
    global original_first_name, original_last_name, original_about

    log.info("سلف‌بات فعال شد!")
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    original_first_name = me.first_name or ""
    original_last_name  = me.last_name or ""

    from telethon.tl.functions.users import GetFullUserRequest
    full = await client(GetFullUserRequest(me))
    original_about = full.full_user.about or ""

    log.info(f"لاگین: {me.first_name}")

    @client.on(events.NewMessage(from_users="me", pattern=r"\.status"))
    async def on_status(event):
        now = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y/%m/%d %H:%M:%S")
        await event.respond(
            f"⏰ تایم‌زون: {TIMEZONE}\n"
            f"⏰ فرمت: {TIME_FORMAT}\n"
            f"⏰ هر {UPDATE_EVERY} ثانیه\n"
            f"⏰ الان: {now}"
        )

    @client.on(events.NewMessage(from_users="me", pattern=r"\.stop"))
    async def on_stop(event):
        await restore_name(client)
        await event.respond("⛔ متوقف شد.")

    @client.on(events.NewMessage(from_users="me", pattern=r"\.setname (.+)"))
    async def on_setname(event):
        global BASE_NAME
        BASE_NAME = event.pattern_match.group(1).strip()
        await event.respond(f"اسم پایه: {BASE_NAME}")

    while True:
        try:
            await update_name(client)
        except Exception as e:
            log.error(f"خطا: {e}")
        await asyncio.sleep(UPDATE_EVERY)


def main():
    if not API_ID or not API_HASH:
        log.error("API_ID و API_HASH لازمه!")
        sys.exit(1)

    if SESSION_STR:
        asyncio.run(run_selfbot())
    elif BOT_TOKEN:
        asyncio.run(run_setup_bot())
    else:
        log.error("SESSION_STRING یا BOT_TOKEN لازمه!")
        sys.exit(1)


if __name__ == "__main__":
    main()