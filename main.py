import os
import sys
import asyncio
import logging
from datetime import datetime

import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ─── متغیرها ────────────────────────────────────────────

API_ID      = int(os.environ.get("API_ID", 0))
API_HASH    = os.environ.get("API_HASH", "")
SESSION_STR = os.environ.get("SESSION_STRING", "")
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
TIMEZONE    = os.environ.get("TIMEZONE", "Asia/Tehran")
TIME_FORMAT = os.environ.get("TIME_FORMAT", "%H:%M")
UPDATE_EVERY = int(os.environ.get("UPDATE_INTERVAL", "60"))
BASE_NAME   = os.environ.get("BASE_NAME", "")
SEPARATOR   = os.environ.get("SEPARATOR", " ǀ ")

# ─── لاگینگ ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

# ─── وضعیت کاربران در حال ستاپ ─────────────────────────

users = {}  # {user_id: {"step": str, "phone": str, ...}}


# ══════════════════════════════════════════════════════════
#  حالت ستاپ — ساخت Session String
# ══════════════════════════════════════════════════════════

async def run_setup_bot():

    log.info(">>> حالت ستاپ شروع شد")

    bot = TelegramClient("setup_session", API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)

    me = await bot.get_me()
    log.info(f">>> ربات فعال: @{me.username}")

    owner_id = [0]  # لیست برای دسترسی داخل closure

    # ── هندلر اصلی: همه پیام‌ها ─────────────────────────

    @bot.on(events.NewMessage)
    async def handle_all(event):

        # فقط پیام‌های خصوصی
        if not event.is_private:
            return

        uid = event.sender_id
        text = event.text.strip()

        # ── /start ──────────────────────────────────────
        if text == "/start":

            # اولین نفر = مالک
            if owner_id[0] == 0:
                owner_id[0] = uid
                log.info(f">>> مالک شناسایی شد: {uid}")

            # فقط مالک
            if uid != owner_id[0]:
                await event.respond("⛔ این ربات مال تو نیست.")
                return

            users[uid] = {"step": "wait_phone"}

            await event.respond(
                "━━━ 🔧 ساخت Session String ━━━\n\n"
                "شماره تلفنت رو بفرست:\n"
                "مثال: `+989123456789`"
            )
            return

        # ── دستورات دیگه رو نادیده بگیر ────────────────
        if text.startswith("/"):
            return

        # ── فقط مالک ───────────────────────────────────
        if uid != owner_id[0]:
            return

        # ── اگه کاربر توی پروسه ستاپ نیست ─────────────
        if uid not in users:
            return

        step = users[uid]["step"]

        # ═══ مرحله: دریافت شماره ═══════════════════════
        if step == "wait_phone":

            if not text.startswith("+") or len(text) < 10:
                await event.respond(
                    "❌ فرمت اشتباه.\n"
                    "مثال: `+989123456789`"
                )
                return

            phone = text
            users[uid]["phone"] = phone
            users[uid]["step"] = "wait_code"

            # ساخت کلاینت موقت
            temp = TelegramClient(StringSession(), API_ID, API_HASH)
            await temp.connect()
            users[uid]["temp"] = temp

            try:
                result = await temp.send_code_request(phone)
                users[uid]["hash"] = result.phone_code_hash
                log.info(f">>> کد ارسال شد به {phone}")
                await event.respond(
                    "📨 کد تایید به تلگرامت ارسال شد.\n\n"
                    "کد رو بفرست:"
                )
            except Exception as e:
                log.error(f">>> خطا ارسال کد: {e}")
                users[uid]["step"] = "wait_phone"
                await temp.disconnect()
                await event.respond(
                    f"❌ خطا: `{e}`\n\n"
                    "دوباره شماره رو بفرست:"
                )
            return

        # ═══ مرحله: دریافت کد ══════════════════════════
        if step == "wait_code":

            code = text.replace(" ", "").replace("-", "")
            if not code.isdigit():
                await event.respond("❌ کد باید عددی باشه.")
                return

            temp = users[uid]["temp"]
            phone = users[uid]["phone"]
            phone_hash = users[uid]["hash"]

            try:
                await temp.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=phone_hash
                )
                log.info(">>> ورود موفق!")

            except Exception as e:
                err = str(e).lower()
                log.error(f">>> خطا ورود: {e}")

                # نیاز به رمز دو مرحله‌ای
                if "password" in err or "2fa" in err:
                    users[uid]["step"] = "wait_2fa"
                    await event.respond(
                        "🔒 رمز دو مرحله‌ای فعاله.\n"
                        "رمز رو بفرست:"
                    )
                    return

                users[uid]["step"] = "wait_phone"
                await temp.disconnect()
                del users[uid]["temp"]
                await event.respond(
                    f"❌ خطا: `{e}`\n\n"
                    "/start رو بزن از اول."
                )
                return

            # ساخت session string
            ss = temp.session.save()
            await temp.disconnect()

            await event.respond(
                "━━━ ✅ سشن ساخته شد! ━━━\n\n"
                "این رشته رو کپی کن:\n\n"
                f"`{ss}`\n\n"
                "━━━ مراحل بعدی ━━━\n\n"
                "1. برو Railway → Variables\n"
                "2. بساز: `SESSION_STRING`\n"
                "3. مقدار: اون رشته‌ای که کپی کردی\n"
                "4. ری‌دیپلوی کن 🚀"
            )

            log.info(">>> Session String ساخته شد!")
            del users[uid]
            return

        # ═══ مرحله: رمز دو مرحله‌ای ════════════════════
        if step == "wait_2fa":

            temp = users[uid]["temp"]

            try:
                await temp.sign_in(password=text)
                ss = temp.session.save()
                await temp.disconnect()

                await event.respond(
                    "━━━ ✅ سشن ساخته شد! ━━━\n\n"
                    "این رشته رو کپی کن:\n\n"
                    f"`{ss}`\n\n"
                    "━━━ مراحل بعدی ━━━\n\n"
                    "1. برو Railway → Variables\n"
                    "2. بساز: `SESSION_STRING`\n"
                    "3. مقدار: اون رشته‌ای که کپی کردی\n"
                    "4. ری‌دیپلوی کن 🚀"
                )

                log.info(">>> Session String ساخته شد!")
                del users[uid]

            except Exception as e:
                log.error(f">>> خطا 2FA: {e}")
                await event.respond(
                    f"❌ رمز اشتباه: `{e}`\n\n"
                    "دوباره رمز رو بفرست:"
                )
            return

    # ── نگه‌داشتن ربات ─────────────────────────────────
    log.info(">>> ربات ستاپ آماده‌ست! منتظر /start ...")
    await bot.run_until_disconnected()


# ══════════════════════════════════════════════════════════
#  حالت سلف‌بات — آپدیت ساعت در اسم
# ══════════════════════════════════════════════════════════

saved_first = ""
saved_last  = ""
saved_about = ""


def time_now():
    return datetime.now(pytz.timezone(TIMEZONE)).strftime(TIME_FORMAT)


async def run_selfbot():

    global saved_first, saved_last, saved_about

    log.info(">>> حالت سلف‌بات شروع شد")

    from telethon.tl.functions.account import UpdateProfileRequest
    from telethon.tl.functions.users import GetFullUserRequest

    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    saved_first = me.first_name or ""
    saved_last  = me.last_name or ""

    full = await client(GetFullUserRequest(me))
    saved_about = full.full_user.about or ""

    log.info(f">>> لاگین: {saved_first} (@{me.username})")

    # ── آپدیت اسم ──────────────────────────────────────

    async def do_update():
        base = BASE_NAME if BASE_NAME else saved_first
        name = f"{base}{SEPARATOR}{time_now()}"
        await client(UpdateProfileRequest(
            first_name=name,
            last_name=saved_last,
            about=saved_about,
        ))
        log.info(f">>> اسم: {name}")

    # ── دستورات ────────────────────────────────────────

    @client.on(events.NewMessage(from_users="me"))
    async def commands(event):

        global BASE_NAME
        text = event.text.strip()

        if text == ".status":
            tz = pytz.timezone(TIMEZONE)
            now = datetime.now(tz).strftime("%Y/%m/%d %H:%M:%S")
            base = BASE_NAME if BASE_NAME else saved_first
            await event.respond(
                f"━━━ وضعیت ━━━\n"
                f"تایم‌زون: {TIMEZONE}\n"
                f"فرمت: {TIME_FORMAT}\n"
                f"بازه: هر {UPDATE_EVERY} ثانیه\n"
                f"ساعت: {now}\n"
                f"اسم پایه: {base}\n"
                f"━━━━━━━━━━━━"
            )

        elif text == ".stop":
            await client(UpdateProfileRequest(
                first_name=saved_first,
                last_name=saved_last,
                about=saved_about,
            ))
            await event.respond("⛔ متوقف شد. اسم اصلی برگردانده شد.")

        elif text.startswith(".setname "):
            BASE_NAME = text[9:].strip()
            await event.respond(f"اسم پایه: {BASE_NAME}")
            await do_update()

    # ── لوپ آپدیت ──────────────────────────────────────

    log.info(f">>> آپدیت هر {UPDATE_EVERY} ثانیه")

    while True:
        try:
            await do_update()
        except Exception as e:
            log.error(f">>> خطا آپدیت: {e}")
        await asyncio.sleep(UPDATE_EVERY)


# ══════════════════════════════════════════════════════════
#  نقطه ورود
# ══════════════════════════════════════════════════════════

def main():

    # بررسی اولیه
    if not API_ID:
        log.error("❌ API_ID تنظیم نشده!")
        sys.exit(1)
    if not API_HASH:
        log.error("❌ API_HASH تنظیم نشده!")
        sys.exit(1)

    log.info(f">>> API_ID: {API_ID}")
    log.info(f">>> API_HASH: {API_HASH[:6]}...")
    log.info(f">>> SESSION_STRING: {'داره' if SESSION_STR else 'نداره'}")
    log.info(f">>> BOT_TOKEN: {'داره' if BOT_TOKEN else 'نداره'}")

    if SESSION_STR:
        log.info(">>> میرم حالت سلف‌بات")
        asyncio.run(run_selfbot())

    elif BOT_TOKEN:
        log.info(">>> میرم حالت ستاپ")
        asyncio.run(run_setup_bot())

    else:
        log.error(
            "❌ یکی از اینا لازمه:\n"
            "   SESSION_STRING (برای سلف‌بات)\n"
            "   BOT_TOKEN (برای ساخت سشن)"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()